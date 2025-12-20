"""
API routes for Ternion gateway.

Implements OpenAI-compatible endpoints for chat completions and models listing.
"""

import structlog
from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response, StreamingResponse

from ternion.core.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Choice,
    MessageRole,
    ModelInfo,
    ModelsListResponse,
)
from ternion.providers.manager import provider_manager
from ternion.router.message_router import MessageRouter
from ternion.utils.streaming import create_sse_stream, stream_sse_chunks

logger = structlog.get_logger(__name__)
router = APIRouter()

# Available Ternion models
TERNION_MODELS = [
    ModelInfo(id="ternion-team", owned_by="ternion"),
    ModelInfo(id="ternion-quick", owned_by="ternion"),
]

# Message router instance
message_router = MessageRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


@router.get("/v1/models")
async def list_models() -> ModelsListResponse:
    """List available models (OpenAI-compatible)."""
    # Include passthrough models from configured providers
    models = list(TERNION_MODELS)

    # Add provider models
    if provider_manager.get_provider("openai"):
        models.append(ModelInfo(id="gpt-4-turbo", owned_by="openai"))
        models.append(ModelInfo(id="gpt-4o", owned_by="openai"))
    if provider_manager.get_provider("anthropic"):
        models.append(ModelInfo(id="claude-3-5-sonnet-latest", owned_by="anthropic"))
        models.append(ModelInfo(id="claude-3-opus-latest", owned_by="anthropic"))
    if provider_manager.get_provider("google"):
        models.append(ModelInfo(id="gemini-2.0-flash", owned_by="google"))
        models.append(ModelInfo(id="gemini-1.5-pro", owned_by="google"))

    return ModelsListResponse(data=models)


@router.post("/v1/chat/completions", response_model=None)
async def chat_completions(
    request: ChatCompletionRequest,
) -> Response:
    """
    Handle chat completion requests (OpenAI-compatible).

    Routes requests based on the model name:
    - ternion-team: Full 4-step discussion flow
    - ternion-quick: Skip final review step
    - gpt-*/claude-*/gemini-*: Direct passthrough to respective provider
    """
    logger.info(
        "chat_completion_request",
        model=request.model,
        message_count=len(request.messages),
        stream=request.stream,
    )

    model = request.model.lower()

    # Check if this is a passthrough request
    if model.startswith("gpt-") or "gpt" in model:
        return await handle_passthrough(request, "openai")
    elif model.startswith("claude-") or "claude" in model:
        return await handle_passthrough(request, "anthropic")
    elif model.startswith("gemini-") or "gemini" in model:
        return await handle_passthrough(request, "google")

    # Extract context using MessageRouter
    context = message_router.extract_context(request.messages)
    logger.debug(
        "context_extracted",
        has_system_prompt=context.cursor_system_prompt is not None,
        history_length=len(context.conversation_history),
    )

    # Check if providers are available
    if not provider_manager.has_providers:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "message": "No LLM providers configured. Please set API keys.",
                    "type": "configuration_error",
                }
            },
        )

    # Run the Ternion discussion workflow
    try:
        from ternion.workflow.graph import run_discussion

        final_state = await run_discussion(context)

        # Get the final output
        output = final_state.get("final_output", "")
        if not output:
            output = final_state.get("generated_code", "")
        if not output:
            output = "[Ternion] Discussion completed but no output was generated."

        # Return response
        if request.stream:
            return StreamingResponse(
                create_sse_stream(model=request.model, content=output),
                media_type="text/event-stream",
            )
        else:
            return JSONResponse(
                content=ChatCompletionResponse(
                    model=request.model,
                    choices=[
                        Choice(
                            message=ChatMessage(
                                role=MessageRole.ASSISTANT,
                                content=output,
                            )
                        )
                    ],
                ).model_dump()
            )
    except Exception as e:
        logger.exception("discussion_error", error=str(e))
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": f"Discussion workflow error: {str(e)}",
                    "type": "workflow_error",
                }
            },
        )


async def handle_passthrough(
    request: ChatCompletionRequest,
    provider_name: str,
) -> Response:
    """
    Handle direct passthrough to a specific provider.

    Args:
        request: The chat completion request
        provider_name: Name of the provider ('openai', 'anthropic', 'google')

    Returns:
        Streaming or JSON response from the provider
    """
    logger.info(
        "passthrough_request",
        model=request.model,
        provider=provider_name,
    )

    provider = provider_manager.get_provider(provider_name)
    if not provider:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "message": f"Provider '{provider_name}' is not configured. "
                    f"Please set the API key in environment variables.",
                    "type": "provider_unavailable",
                }
            },
        )

    try:
        if request.stream:
            # Streaming response
            async def stream_generator():
                async for chunk in provider.chat_completion_stream(
                    messages=request.messages,
                    model=request.model,
                    temperature=request.temperature or 0.7,
                    max_tokens=request.max_tokens,
                ):
                    yield chunk

            return StreamingResponse(
                stream_sse_chunks(stream_generator()),
                media_type="text/event-stream",
            )
        else:
            # Non-streaming response
            response = await provider.chat_completion(
                messages=request.messages,
                model=request.model,
                temperature=request.temperature or 0.7,
                max_tokens=request.max_tokens,
            )

            return JSONResponse(
                content=ChatCompletionResponse(
                    model=request.model,
                    choices=[
                        Choice(
                            message=ChatMessage(
                                role=MessageRole.ASSISTANT,
                                content=response.content,
                            ),
                            finish_reason=response.finish_reason or "stop",
                        )
                    ],
                    usage=response.usage,
                ).model_dump()
            )
    except Exception as e:
        logger.exception("passthrough_error", provider=provider_name, error=str(e))
        return JSONResponse(
            status_code=502,
            content={
                "error": {
                    "message": f"Provider error: {str(e)}",
                    "type": "provider_error",
                }
            },
        )
