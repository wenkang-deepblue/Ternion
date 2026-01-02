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
from ternion.core.budget import budget_manager
from ternion.providers.manager import provider_manager
from ternion.router.message_router import MessageRouter
from ternion.utils.streaming import create_sse_stream, stream_sse_chunks

logger = structlog.get_logger(__name__)
router = APIRouter()

# Available Ternion models
TERNION_MODELS = [
    ModelInfo(id="ternion-team", owned_by="ternion"),
    # ModelInfo(id="ternion-quick", owned_by="ternion"),  # Coming Soon
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
    - ternion-quick: Coming Soon (skip final review step)
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
                    "message": "No LLM providers configured. "
                    "Please add API keys in the Web Control Panel at http://localhost:7990",
                    "type": "configuration_error",
                }
            },
        )

    # Check role configuration completeness
    from ternion.core.config_store import config_store
    
    user_config = config_store.load()
    missing_roles = []
    role_names = {"arbiter": "Arbiter", "writer": "Writer", "reviewer": "Reviewer"}
    
    for role, display_name in role_names.items():
        role_config = user_config.roles.get(role)
        if not role_config:
            missing_roles.append(display_name)
            continue
        # Check if the provider for this role is enabled
        provider_config = user_config.providers.get(role_config.provider)
        if not provider_config or not provider_config.api_keys or not provider_config.selected_key_id:
            missing_roles.append(f"{display_name} ({role_config.provider} not configured)")
    
    if missing_roles:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "message": f"Role configuration incomplete. Please configure: {', '.join(missing_roles)}. "
                               f"Visit http://localhost:7990 to complete setup.",
                    "type": "configuration_error",
                }
            },
        )

    # Check budget before proceeding
    budget_ok, budget_warning = budget_manager.check_budget(estimated_cost=0.15)
    if not budget_ok:
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "message": budget_warning or "Budget exceeded",
                    "type": "budget_exceeded",
                }
            },
        )

    # Run the Ternion discussion workflow
    try:
        from ternion.workflow.graph import run_discussion

        final_state = await run_discussion(context)

        # Build output with thinking logs + final code
        thinking_logs = final_state.get("thinking_logs", [])
        final_code = final_state.get("final_output", "") or final_state.get("generated_code", "")
        
        # Combine thinking stream with final output
        output_parts = []
        
        # Add budget warning if approaching limit
        if budget_warning:
            output_parts.append(budget_manager.format_budget_warning(budget_warning))
        
        # Add thinking logs (Cursor-compatible markdown)
        if thinking_logs:
            output_parts.append("".join(thinking_logs))
            output_parts.append("\n---\n\n")  # Separator
        
        # Add final output
        if final_code:
            output_parts.append(final_code)
        else:
            output_parts.append("[Ternion] Discussion completed but no output was generated.")
        
        output = "".join(output_parts)

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
                    f"Please add your API key in the Web Control Panel at http://localhost:7990",
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

            # Track usage if available
            if response.usage:
                usage_data = response.usage or {}
                prompt_tokens = (
                    usage_data.get("prompt_tokens")
                    or usage_data.get("input_tokens")
                    or 0
                )
                completion_tokens = (
                    usage_data.get("completion_tokens")
                    or usage_data.get("output_tokens")
                    or 0
                )
                thoughts_tokens = usage_data.get("thoughts_tokens") or usage_data.get("reasoning_tokens") or 0
                total_tokens = usage_data.get("total_tokens", 0)
                if provider_name == "google":
                    output_for_cost = completion_tokens + thoughts_tokens
                else:
                    output_for_cost = completion_tokens
                budget_manager.record_usage(
                    provider=provider_name,
                    model=request.model,
                    input_tokens=prompt_tokens,
                    output_tokens=output_for_cost,
                    thoughts_tokens=thoughts_tokens,
                    context_length=total_tokens,
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
