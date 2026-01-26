"""
Internationalization (i18n) module for Ternion backend.

Provides localized messages for thinking stream logs and other user-facing
backend text. Language preference is stored in user configuration.
"""

from enum import Enum
from typing import Literal

from ternion.core.config_store import config_store

Language = Literal["en", "zh", "es", "fr", "de", "ja", "ko"]


class MessageKey(str, Enum):
    """Keys for localized messages (logs, errors, UI text)."""

    # Evidence Stage Errors
    EVIDENCE_COLLECTION_FAILED = "evidence_collection_failed"
    REPORT_EVIDENCE_COLLECTION_FAILED = "report_evidence_collection_failed"

    DIVERGENCE_START = "divergence_start"
    DIVERGENCE_ANALYSIS = "divergence_analysis"
    DIVERGENCE_ANALYSIS_FAILED = "divergence_analysis_failed"
    CONVERGENCE_START = "convergence_start"
    CONVERGENCE_COMPLETE = "convergence_complete"
    CONVERGENCE_ERROR = "convergence_error"
    CONVERGENCE_ALL_ARBITERS_FAILED = "convergence_all_arbiters_failed"
    EXECUTION_START = "execution_start"
    EXECUTION_COMPLETE = "execution_complete"
    EXECUTION_ERROR = "execution_error"
    OPTIMIZER_START = "optimizer_start"
    OPTIMIZER_OUTPUT_PROTOCOL_ERROR = "optimizer_output_protocol_error"
    REVIEW_START = "review_start"
    REVIEW_APPROVED = "review_approved"
    REVIEW_REVISION = "review_revision"
    FINAL_CHECK_ERROR = "final_check_error"

    # Convergence Fallback
    CONVERGENCE_FALLBACK_WARNING = "convergence_fallback_warning"
    CONVERGENCE_FALLBACK_CONFIRM = "convergence_fallback_confirm"

    # Validation Errors
    EXECUTION_MODE_MISSING = "execution_mode_missing"
    ROLE_CONFIG_INCOMPLETE = "role_config_incomplete"
    EXECUTION_REQUIRES_AGENT_MODE = "execution_requires_agent_mode"
    IMPLEMENTATION_STAGE_MISSING_FIELDS = "implementation_stage_missing_fields"

    # Provider Manager Errors
    NO_PROVIDERS_CONFIGURED = "no_providers_configured"
    ROLE_NOT_CONFIGURED = "role_not_configured"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    EXECUTION_MODE_NOT_CONFIGURED = "execution_mode_not_configured"
    UNSUPPORTED_MODEL = "unsupported_model"
    NO_TERNION_ANALYSES_AVAILABLE = "no_ternion_analyses_available"

    # Budget Alerts
    BUDGET_WARNING = "budget_warning"
    BUDGET_EXCEEDED = "budget_exceeded"
    BUDGET_EXCEEDED_ERROR = "budget_exceeded_error"
    BUDGET_CONFIRM_REQUIRED = "budget_confirm_required"
    LOG_BUDGET_WARNING = "log_budget_warning"
    LOG_BUDGET_EXCEEDED = "log_budget_exceeded"
    LOG_BUDGET_IMPL_BLOCKED = "log_budget_impl_blocked"
    LOG_BUDGET_CONFIRM_REQUIRED = "log_budget_confirm_required"

    # Tool Loop Guardrails
    TOOL_LOOP_FAILSAFE_REACHED = "tool_loop_failsafe_reached"
    LOG_TOOL_LOOP_FAILSAFE_REACHED = "log_tool_loop_failsafe_reached"
    DELIVERABLE_POLICY_BLOCKED = "deliverable_policy_blocked"
    EXECUTION_TOOL_POLICY_BLOCKED = "execution_tool_policy_blocked"
    EVIDENCE_TOPUP_FINAL_REQUIRED = "evidence_topup_final_required"
    EVIDENCE_TOPUP_LIMIT_REACHED = "evidence_topup_limit_reached"
    EVIDENCE_TOPUP_REQUESTS_EMPTY = "evidence_topup_requests_empty"
    EVIDENCE_TOPUP_PURPOSE_REQUIRED = "evidence_topup_purpose_required"

    # Discussion Output (Cursor-facing UI text)
    DISCUSSION_NO_OUTPUT = "discussion_no_output"
    DISCUSSION_ERRORS_HEADER = "discussion_errors_header"

    # Streaming Errors (Cursor-facing UI text)
    STREAM_ERROR_GENERIC = "stream_error_generic"
    STREAM_ERROR_INTERRUPTED = "stream_error_interrupted"

    # Report Display (Cursor-facing UI text)
    REPORT_SECTION_ROOT_CAUSE_TITLE = "report_section_root_cause_title"
    REPORT_SECTION_EVIDENCE_TITLE = "report_section_evidence_title"
    REPORT_SECTION_SCOPE_TITLE = "report_section_scope_title"
    REPORT_SECTION_FIX_PLAN_TITLE = "report_section_fix_plan_title"
    REPORT_SECTION_VERIFICATION_TITLE = "report_section_verification_title"
    REPORT_SECTION_RISKS_TITLE = "report_section_risks_title"
    REPORT_SECTION_IF_NOT_EFFECTIVE_TITLE = "report_section_if_not_effective_title"
    REPORT_SECTION_MISSING_PLACEHOLDER = "report_section_missing_placeholder"
    REPORT_RAW_SESSION_NOTE = "report_raw_session_note"
    REPORT_CONFIRM_PROMPT = "report_confirm_prompt"
    REPORT_CONFIRM_PROMPT_CURSOR_HANDOFF = "report_confirm_prompt_cursor_handoff"
    EXECUTION_MODE_DESC_TERNION_FULL = "execution_mode_desc_ternion_full"
    EXECUTION_MODE_DESC_CURSOR_HANDOFF = "execution_mode_desc_cursor_handoff"


TRANSLATIONS: dict[Language, dict[str, str]] = {
    "en": {
        # Evidence Stage Errors
        MessageKey.EVIDENCE_COLLECTION_FAILED: "Evidence collection failed: {error}",
        MessageKey.REPORT_EVIDENCE_COLLECTION_FAILED: "Report evidence collection failed: {error}",

        MessageKey.DIVERGENCE_START: "> **[Arbiter]**: Starting parallel problem analysis...\n",
        MessageKey.DIVERGENCE_ANALYSIS: "> **[{ternion_id}]**: {preview}\n",
        MessageKey.DIVERGENCE_ANALYSIS_FAILED: "> **[{ternion_id}]**: Analysis failed ({provider}): {error}\n",
        MessageKey.CONVERGENCE_START: "> **[Arbiter]**: Synthesizing opinions, generating report...\n",
        MessageKey.CONVERGENCE_COMPLETE: "> **[Arbiter]**: Report complete: {preview}\n",
        MessageKey.CONVERGENCE_ERROR: "> **[Arbiter]**: Error during convergence: {error}\n",
        MessageKey.CONVERGENCE_ALL_ARBITERS_FAILED: "All Arbiters failed; using raw analysis.",
        MessageKey.EXECUTION_START: "> **[Writer]**: Generating code from analysis report...\n",
        MessageKey.EXECUTION_COMPLETE: "> **[Writer]**: Code generation complete\n",
        MessageKey.EXECUTION_ERROR: "> **[Writer]**: Error during execution: {error}\n",
        MessageKey.OPTIMIZER_START: (
            "> **[Optimizer]**: Validating and improving code against Ternion Report acceptance criteria...\n"
        ),
        MessageKey.OPTIMIZER_OUTPUT_PROTOCOL_ERROR: (
            "\n[Ternion] Optimizer output protocol error: missing user summary wrapper. "
            "The internal optimizer report was captured. Please retry.\n"
        ),
        MessageKey.REVIEW_START: "> **[Reviewer]**: Reviewing code security and logic...\n",
        MessageKey.REVIEW_APPROVED: "> **[Reviewer]**: Review passed\n",
        MessageKey.REVIEW_REVISION: "> **[Reviewer]**: Revision needed, returning to Writer...\n",
        MessageKey.FINAL_CHECK_ERROR: "> **[Reviewer]**: Error during review: {error}\n",

        # Convergence Fallback
        MessageKey.CONVERGENCE_FALLBACK_WARNING: (
            "> **Note**: This report was generated using a single analysis (fallback mode) "
            "because the Arbiter synthesis failed. The analysis may be less comprehensive than usual."
        ),
        MessageKey.CONVERGENCE_FALLBACK_CONFIRM: (
            "Please review the analysis above. If correct, reply with your confirmation to proceed with implementation handoff to Cursor.\n"
            "If you disagree or need adjustments, describe the issues and I will re-analyze."
        ),

        # Validation Errors
        MessageKey.EXECUTION_MODE_MISSING: (
            "Execution mode not configured. Please open Web Control Panel to configure: "
            "{web_url} (Config -> Execution Mode -> Save)"
        ),
        MessageKey.ROLE_CONFIG_INCOMPLETE: (
            "Role model configuration incomplete. Please configure: {missing_roles}. "
            "Please open Web Control Panel: {web_url}"
        ),
        MessageKey.EXECUTION_REQUIRES_AGENT_MODE: (
            "This request is in a non-Agent Cursor mode (Ask/Plan/Debug). "
            "Execution requires Cursor Agent mode. Please switch to Agent mode and confirm again."
        ),
        MessageKey.IMPLEMENTATION_STAGE_MISSING_FIELDS: (
            "[Ternion] Implementation stage cannot proceed: missing required fields: {missing_fields}"
        ),

        # Provider Manager Errors
        MessageKey.NO_PROVIDERS_CONFIGURED: "Please add API keys in the Web Control Panel at {web_url}",
        MessageKey.ROLE_NOT_CONFIGURED: "Role '{role}' is not configured. Please configure it in the Web Control Panel at {web_url}",
        MessageKey.PROVIDER_UNAVAILABLE: "Provider '{provider}' for role '{role}' is not available. Please add an API key for {provider} in the Web Control Panel.",
        MessageKey.EXECUTION_MODE_NOT_CONFIGURED: "Execution mode not configured. Please choose and save it in the Web Control Panel ({web_url} -> Config -> Execution Mode).",
        MessageKey.UNSUPPORTED_MODEL: (
            "Unsupported model: '{model}'. This Ternion gateway only supports 'ternion-team'. "
            "If you intended to use Cursor's subscription-included GPT/Claude/Gemini models, please disable "
            "\"OpenAI API Key\" and \"Override OpenAI Base URL\" in Cursor Settings "
            "(Settings --> Models --> \"OpenAI API Key\" & \"Override OpenAI Base URL\"). "
            "If you intended to use Ternion, switch the model to 'ternion-team'."
        ),
        MessageKey.NO_TERNION_ANALYSES_AVAILABLE: "No ternion analyses available.",

        # Budget Alerts
        MessageKey.BUDGET_WARNING: (
            "\n> **[Ternion Budget Alert]**: Monthly usage has reached **{usage_pct}%**, "
            "approaching budget limit. This request may exceed monthly budget.\n"
            "> View usage details in Control Panel -> Usage page.\n\n"
        ),
        MessageKey.BUDGET_EXCEEDED: (
            "\n> **[Ternion Budget Exceeded]**: Monthly budget exhausted, request blocked.\n"
            "> Adjust budget settings in Control Panel -> Config page.\n\n"
        ),
        MessageKey.BUDGET_EXCEEDED_ERROR: "Monthly budget exhausted. Adjust budget in Control Panel -> Config page.",
        MessageKey.BUDGET_CONFIRM_REQUIRED: (
            "\n> **[Ternion Budget Alert]**: Monthly usage has reached **{usage_pct}%**. "
            "Reply with \"continue\" to proceed with the tool loop, or adjust budget settings "
            "in Control Panel -> Config page.\n"
        ),
        MessageKey.LOG_BUDGET_WARNING: "Budget warning | usage={usage_pct}% | Approaching monthly limit",
        MessageKey.LOG_BUDGET_EXCEEDED: "Budget exceeded | Request blocked | Monthly limit reached",
        MessageKey.LOG_BUDGET_IMPL_BLOCKED: "Budget exceeded | Implementation blocked | session_id={session_id}",
        MessageKey.LOG_BUDGET_CONFIRM_REQUIRED: "Budget warning | confirmation required | usage={usage_pct}%",

        # Tool Loop Guardrails
        MessageKey.TOOL_LOOP_FAILSAFE_REACHED: (
            "\n> **[Ternion]**: Tool loop reached the failsafe limit ({max_rounds}). "
            "Please narrow scope or provide exact file paths/line ranges, then start a new request.\n"
        ),
        MessageKey.LOG_TOOL_LOOP_FAILSAFE_REACHED: (
            "Tool loop failsafe reached | max_rounds={max_rounds} | session_id={session_id}"
        ),
        MessageKey.DELIVERABLE_POLICY_BLOCKED: (
            "[Ternion] Deliverable policy blocked mutation tool calls.\n"
            "Deliverable type: {deliverable_type}\n"
            "Allowed write scope: {allowed_scope}\n"
            "Blocked targets:\n{blocked_targets}\n"
            "Note: Mutation targets must be inside the project root and within the allowed write scope.\n"
        ),
        MessageKey.EXECUTION_TOOL_POLICY_BLOCKED: (
            "[Ternion] Tool policy blocked Execution/Optimizer tool calls.\n"
            "Blocked tools:\n{blocked_tools}\n"
            "Blocked shell commands:\n{blocked_shell}\n"
        ),
        MessageKey.EVIDENCE_TOPUP_FINAL_REQUIRED: (
            "[Ternion] Evidence top-up request rejected: the 2nd request must be marked as the final request.\n"
            "Please re-issue the request with FINAL_REQUEST: true.\n"
        ),
        MessageKey.EVIDENCE_TOPUP_LIMIT_REACHED: (
            "[Ternion] Evidence top-up limit reached ({max_rounds}). Further evidence requests are not allowed.\n"
            "Please proceed with the deliverable using the existing evidence.\n"
        ),
        MessageKey.EVIDENCE_TOPUP_REQUESTS_EMPTY: (
            "[Ternion] Evidence top-up request rejected: the requests block contains no actionable evidence requests.\n"
            "Please provide at least one request line and one PURPOSE line per request.\n"
        ),
        MessageKey.EVIDENCE_TOPUP_PURPOSE_REQUIRED: (
            "[Ternion] Evidence top-up request rejected: every request must include a PURPOSE line.\n"
            "Missing PURPOSE for:\n{missing_items}\n"
        ),

        # Discussion Output (Cursor-facing UI text)
        MessageKey.DISCUSSION_NO_OUTPUT: "[Ternion] Discussion completed but no output was generated.",
        MessageKey.DISCUSSION_ERRORS_HEADER: "[Ternion] Errors:\n",
        MessageKey.STREAM_ERROR_GENERIC: "\n\n[Ternion] Streaming error occurred. Please retry.\n",
        MessageKey.STREAM_ERROR_INTERRUPTED: "\n\n[Ternion] Streaming interrupted. Please retry.\n",

        # Report Display (Cursor-facing UI text)
        MessageKey.REPORT_SECTION_ROOT_CAUSE_TITLE: "Root Cause",
        MessageKey.REPORT_SECTION_EVIDENCE_TITLE: "Evidence / Logs",
        MessageKey.REPORT_SECTION_SCOPE_TITLE: "Scope & Non-Goals",
        MessageKey.REPORT_SECTION_FIX_PLAN_TITLE: "Fix Plan / Recommendation",
        MessageKey.REPORT_SECTION_VERIFICATION_TITLE: "Verification",
        MessageKey.REPORT_SECTION_RISKS_TITLE: "Risks & Rollback",
        MessageKey.REPORT_SECTION_IF_NOT_EFFECTIVE_TITLE: "If not effective, then what?",
        MessageKey.REPORT_SECTION_MISSING_PLACEHOLDER: "(Missing)",
        MessageKey.REPORT_RAW_SESSION_NOTE: "Original Markdown report is stored in the local Session: {path} (field: {field})",
        MessageKey.EXECUTION_MODE_DESC_TERNION_FULL: "code implementation by Ternion",
        MessageKey.EXECUTION_MODE_DESC_CURSOR_HANDOFF: "implementation handoff to Cursor",
        MessageKey.REPORT_CONFIRM_PROMPT: (
            "Please review the analysis above. If correct, reply with your confirmation to proceed with {mode_desc}.\n"
            "If you disagree or need adjustments, describe the issues and I will re-analyze."
        ),
        MessageKey.REPORT_CONFIRM_PROMPT_CURSOR_HANDOFF: (
            "You are using \"Ternion Root Cause Analysis + Cursor Implementation\" mode. "
            "Please review the analysis above. If correct, go to Cursor Settings, disable the \"OpenAI API Key\" switch, "
            "select a Cursor native model (Gemini, Claude, or GPT series), then reply with your confirmation to proceed "
            "with implementation handoff to Cursor.\n"
            "If you disagree or need adjustments, describe the issues and I will re-analyze."
        ),
    },
    "zh": {
        # Evidence Stage Errors
        MessageKey.EVIDENCE_COLLECTION_FAILED: "证据采集失败：{error}",
        MessageKey.REPORT_EVIDENCE_COLLECTION_FAILED: "报告阶段证据补齐失败：{error}",

        MessageKey.DIVERGENCE_START: "> **[Arbiter]**: 开始并发问题分析...\n",
        MessageKey.DIVERGENCE_ANALYSIS: "> **[{ternion_id}]**: {preview}\n",
        MessageKey.DIVERGENCE_ANALYSIS_FAILED: "> **[{ternion_id}]**: 分析失败（{provider}）：{error}\n",
        MessageKey.CONVERGENCE_START: "> **[Arbiter]**: 综合分析各方意见，生成报告...\n",
        MessageKey.CONVERGENCE_COMPLETE: "> **[Arbiter]**: 报告生成完成: {preview}\n",
        MessageKey.CONVERGENCE_ERROR: "> **[Arbiter]**: 综合分析错误: {error}\n",
        MessageKey.CONVERGENCE_ALL_ARBITERS_FAILED: "所有 Arbiter 失败，使用原始分析作为回退。",
        MessageKey.EXECUTION_START: "> **[Writer]**: 基于分析报告生成代码中...\n",
        MessageKey.EXECUTION_COMPLETE: "> **[Writer]**: 代码生成完成\n",
        MessageKey.EXECUTION_ERROR: "> **[Writer]**: 代码生成错误: {error}\n",
        MessageKey.OPTIMIZER_START: "> **[Optimizer]**: 基于Ternion Report的验收标准校验并改进代码中...\n",
        MessageKey.OPTIMIZER_OUTPUT_PROTOCOL_ERROR: (
            "\n[Ternion] Optimizer 输出协议错误：未生成用户可见的工作总结包装段。"
            "内部 Optimizer 报告已落盘抓包，请重试。\n"
        ),
        MessageKey.REVIEW_START: "> **[Reviewer]**: 审查代码安全性和逻辑...\n",
        MessageKey.REVIEW_APPROVED: "> **[Reviewer]**: 审查通过\n",
        MessageKey.REVIEW_REVISION: "> **[Reviewer]**: 需要修订，返回 Writer 重写...\n",
        MessageKey.FINAL_CHECK_ERROR: "> **[Reviewer]**: 审查错误: {error}\n",

        # Convergence Fallback
        MessageKey.CONVERGENCE_FALLBACK_WARNING: (
            "> **注意**: 此报告由单个分析生成（降级模式），因为 Arbiter 综合分析失败。"
            "分析结果可能不如正常情况全面。"
        ),
        MessageKey.CONVERGENCE_FALLBACK_CONFIRM: (
            "请审阅以上分析。如确认无误，请回复确认以继续将实现任务交接给 Cursor。\n"
            "如有异议或需要调整，请描述问题，我将重新分析。"
        ),

        # Validation Errors
        MessageKey.EXECUTION_MODE_MISSING: (
            "执行模式未配置。请打开 Web 控制面板配置："
            "{web_url}（配置 -> 推理方案 -> 保存）"
        ),
        MessageKey.ROLE_CONFIG_INCOMPLETE: (
            "角色模型配置不完整，缺少：{missing_roles}。"
            "请打开 Web 控制面板：{web_url}"
        ),
        MessageKey.EXECUTION_REQUIRES_AGENT_MODE: (
            "当前处于 Cursor 的非 Agent 模式（Ask/Plan/Debug）。执行/改代码需要 Cursor Agent 模式。"
            "请切换到 Agent 模式后再次发送确认以继续。"
        ),
        MessageKey.IMPLEMENTATION_STAGE_MISSING_FIELDS: (
            "[Ternion] 实现阶段无法继续：缺少必需字段：{missing_fields}"
        ),

        # Provider Manager Errors
        MessageKey.NO_PROVIDERS_CONFIGURED: "请在 Web 控制面板添加 API Key：{web_url}",
        MessageKey.ROLE_NOT_CONFIGURED: "角色 '{role}' 未配置。请在 Web 控制面板配置：{web_url}",
        MessageKey.PROVIDER_UNAVAILABLE: "角色 '{role}' 的提供商 '{provider}' 不可用。请在 Web 控制面板为 {provider} 添加 API Key。",
        MessageKey.EXECUTION_MODE_NOT_CONFIGURED: "执行模式未配置。请在 Web 控制面板选择并保存（{web_url} -> 配置 -> 推理方案选择）。",
        MessageKey.UNSUPPORTED_MODEL: (
            "不支持的模型：'{model}'。当前 Ternion 网关仅支持 'ternion-team'。"
            "如果你想使用 Cursor 订阅内置的 GPT/Claude/Gemini 模型，请在 Cursor 设置中关闭 "
            "\"OpenAI API Key\" 以及 \"Override OpenAI Base URL\" "
            "(设置 --> Models --> \"OpenAI API Key\" & \"Override OpenAI Base URL\")。"
            "如果你想使用 Ternion，请将模型切换为 'ternion-team'。"
        ),
        MessageKey.NO_TERNION_ANALYSES_AVAILABLE: "没有可用的 Ternion 分析结果。",

        # Budget Alerts
        MessageKey.BUDGET_WARNING: (
            "\n> **[Ternion 预算警报]**：当前月度用量已达 **{usage_pct}%**，"
            "接近预算上限。此次请求可能导致超出月度预算。\n"
            "> 可在 Control Panel 的「用量」页面查看详细用量日志。\n\n"
        ),
        MessageKey.BUDGET_EXCEEDED: (
            "\n> **[Ternion 预算超限]**：月度预算已耗尽，请求已被拦截。\n"
            "> 请在 Control Panel 的「配置」页面调整预算设置。\n\n"
        ),
        MessageKey.BUDGET_EXCEEDED_ERROR: "月度预算已耗尽，请求已被拦截。请在 Control Panel 的「配置」页面调整预算设置。",
        MessageKey.BUDGET_CONFIRM_REQUIRED: (
            "\n> **[Ternion 预算警报]**：当前月度用量已达 **{usage_pct}%**。"
            "如需继续工具循环，请回复“继续”；或在 Control Panel 的「配置」页面调整预算设置。\n"
        ),
        MessageKey.LOG_BUDGET_WARNING: "预算警告 | 用量={usage_pct}% | 接近月度上限",
        MessageKey.LOG_BUDGET_EXCEEDED: "预算超限 | 请求已拦截 | 月度上限已达",
        MessageKey.LOG_BUDGET_IMPL_BLOCKED: "预算超限 | 实现阶段已阻止 | session_id={session_id}",
        MessageKey.LOG_BUDGET_CONFIRM_REQUIRED: "预算警告 | 需要确认继续 | 用量={usage_pct}%",

        # Tool Loop Guardrails
        MessageKey.TOOL_LOOP_FAILSAFE_REACHED: (
            "\n> **[Ternion]**：工具循环已达到 failsafe 上限（{max_rounds}）。"
            "请缩小范围或提供精确文件路径/行号范围后重新发起请求。\n"
        ),
        MessageKey.LOG_TOOL_LOOP_FAILSAFE_REACHED: (
            "工具循环 failsafe 触发 | max_rounds={max_rounds} | session_id={session_id}"
        ),
        MessageKey.DELIVERABLE_POLICY_BLOCKED: (
            "[Ternion] 交付物类型策略阻止了本次写入工具调用。\n"
            "交付物类型：{deliverable_type}\n"
            "允许写入范围：{allowed_scope}\n"
            "被阻止的目标：\n{blocked_targets}\n"
            "说明：所有写入目标必须位于项目根目录内，并且必须符合允许写入范围。\n"
        ),
        MessageKey.EXECUTION_TOOL_POLICY_BLOCKED: (
            "[Ternion] 工具策略阻止了 Execution/Optimizer 的工具调用。\n"
            "被阻止的工具：\n{blocked_tools}\n"
            "被阻止的 Shell 命令：\n{blocked_shell}\n"
        ),
        MessageKey.EVIDENCE_TOPUP_FINAL_REQUIRED: (
            "[Ternion] 证据补齐请求被拒绝：第 2 次补证据请求必须声明为最后一次。\n"
            "请在协议块中设置 FINAL_REQUEST: true 后重试。\n"
        ),
        MessageKey.EVIDENCE_TOPUP_LIMIT_REACHED: (
            "[Ternion] 证据补齐次数已达到上限（{max_rounds}）。系统将不再进入证据补齐流程。\n"
            "请基于现有证据继续完成交付。\n"
        ),
        MessageKey.EVIDENCE_TOPUP_REQUESTS_EMPTY: (
            "[Ternion] 证据补齐请求被拒绝：协议块中未包含可执行的证据请求。\n"
            "请至少提供 1 条请求行，并为每条请求紧跟 1 行 PURPOSE。\n"
        ),
        MessageKey.EVIDENCE_TOPUP_PURPOSE_REQUIRED: (
            "[Ternion] 证据补齐请求被拒绝：每条请求都必须包含 PURPOSE 行。\n"
            "缺失 PURPOSE 的请求：\n{missing_items}\n"
        ),

        # Discussion Output (Cursor-facing UI text)
        MessageKey.DISCUSSION_NO_OUTPUT: "[Ternion] 流程已完成，但未生成任何输出。",
        MessageKey.DISCUSSION_ERRORS_HEADER: "[Ternion] 错误：\n",
        MessageKey.STREAM_ERROR_GENERIC: "\n\n[Ternion] 流式输出发生错误，请重试。\n",
        MessageKey.STREAM_ERROR_INTERRUPTED: "\n\n[Ternion] 流式输出中断，请重试。\n",

        # Report Display (Cursor-facing UI text)
        MessageKey.REPORT_SECTION_ROOT_CAUSE_TITLE: "根因",
        MessageKey.REPORT_SECTION_EVIDENCE_TITLE: "证据/日志",
        MessageKey.REPORT_SECTION_SCOPE_TITLE: "范围/非目标",
        MessageKey.REPORT_SECTION_FIX_PLAN_TITLE: "方案/建议",
        MessageKey.REPORT_SECTION_VERIFICATION_TITLE: "验证",
        MessageKey.REPORT_SECTION_RISKS_TITLE: "风险/回滚",
        MessageKey.REPORT_SECTION_IF_NOT_EFFECTIVE_TITLE: "若无效，下一步",
        MessageKey.REPORT_SECTION_MISSING_PLACEHOLDER: "（缺失）",
        MessageKey.REPORT_RAW_SESSION_NOTE: "原始 Markdown 报告已保存在本地 Session：{path}（字段：{field}）",
        MessageKey.EXECUTION_MODE_DESC_TERNION_FULL: "由 Ternion 执行代码实现",
        MessageKey.EXECUTION_MODE_DESC_CURSOR_HANDOFF: "将实现任务交接给 Cursor",
        MessageKey.REPORT_CONFIRM_PROMPT: (
            "请审阅以上分析。如确认无误，请回复确认以继续{mode_desc}。\n"
            "如有异议或需要调整，请描述问题，我将重新分析。"
        ),
        MessageKey.REPORT_CONFIRM_PROMPT_CURSOR_HANDOFF: (
            "您正在使用「Ternion 问题归因 + Cursor 代码实现」模式。"
            "请审阅以上分析，如确认无误，请在 Cursor 设置中关闭「OpenAI API Key」开关，"
            "选择 Cursor 原生模型（Gemini、Claude 或 GPT 系列），然后回复确认以继续将代码实现任务交给 Cursor 完成。\n"
            "如有异议或需要调整，请描述问题，我将重新分析。"
        ),
    },
    "es": {
        # Evidence Stage Errors
        MessageKey.EVIDENCE_COLLECTION_FAILED: "La recopilación de evidencias falló: {error}",
        MessageKey.REPORT_EVIDENCE_COLLECTION_FAILED: "La verificación de evidencias del informe falló: {error}",

        MessageKey.DIVERGENCE_START: "> **[Árbitro]**: Iniciando análisis paralelo del problema...\n",
        MessageKey.DIVERGENCE_ANALYSIS: "> **[{ternion_id}]**: {preview}\n",
        MessageKey.DIVERGENCE_ANALYSIS_FAILED: "> **[{ternion_id}]**: El análisis falló ({provider}): {error}\n",
        MessageKey.CONVERGENCE_START: "> **[Árbitro]**: Sintetizando opiniones, generando informe...\n",
        MessageKey.CONVERGENCE_COMPLETE: "> **[Árbitro]**: Informe completo: {preview}\n",
        MessageKey.CONVERGENCE_ERROR: "> **[Árbitro]**: Error durante convergencia: {error}\n",
        MessageKey.CONVERGENCE_ALL_ARBITERS_FAILED: "Todos los Árbitros fallaron; usando el análisis en bruto.",
        MessageKey.EXECUTION_START: "> **[Escritor]**: Generando código del informe de análisis...\n",
        MessageKey.EXECUTION_COMPLETE: "> **[Escritor]**: Generación de código completa\n",
        MessageKey.EXECUTION_ERROR: "> **[Escritor]**: Error durante ejecución: {error}\n",
        MessageKey.OPTIMIZER_START: "> **[Optimizador]**: Validando y mejorando la implementación...\n",
        MessageKey.OPTIMIZER_OUTPUT_PROTOCOL_ERROR: (
            "\n[Ternion] Error de protocolo en la salida del optimizador: falta el bloque de resumen para el usuario. "
            "El informe interno del optimizador fue capturado. Inténtalo de nuevo.\n"
        ),
        MessageKey.REVIEW_START: "> **[Revisor]**: Revisando seguridad y lógica del código...\n",
        MessageKey.REVIEW_APPROVED: "> **[Revisor]**: Revisión aprobada\n",
        MessageKey.REVIEW_REVISION: "> **[Revisor]**: Revisión necesaria, regresando a Escritor...\n",
        MessageKey.FINAL_CHECK_ERROR: "> **[Revisor]**: Error durante revisión: {error}\n",

        # Convergence Fallback
        MessageKey.CONVERGENCE_FALLBACK_WARNING: (
            "> **Nota**: Este informe fue generado usando un solo análisis (modo de respaldo) "
            "porque la síntesis del Árbitro falló. El análisis puede ser menos completo de lo habitual."
        ),
        MessageKey.CONVERGENCE_FALLBACK_CONFIRM: (
            "Por favor revise el análisis anterior. Si es correcto, responda con su confirmación para proceder con la entrega de implementación a Cursor.\n"
            "Si no está de acuerdo o necesita ajustes, describa los problemas y volveré a analizar."
        ),

        # Validation Errors
        MessageKey.EXECUTION_MODE_MISSING: (
            "Modo de ejecución no configurado. Por favor abra el Panel de Control Web: "
            "{web_url} (Configuración -> Modo de Ejecución -> Guardar)"
        ),
        MessageKey.ROLE_CONFIG_INCOMPLETE: (
            "Configuración de modelo de rol incompleta. Por favor configure: {missing_roles}. "
            "Abra el Panel de Control Web: {web_url}"
        ),
        MessageKey.EXECUTION_REQUIRES_AGENT_MODE: (
            "Esta solicitud está en un modo no-Agent de Cursor (Ask/Plan/Debug). "
            "La ejecución requiere el modo Agent. Cambie a Agent y confirme de nuevo."
        ),
        MessageKey.IMPLEMENTATION_STAGE_MISSING_FIELDS: (
            "[Ternion] La etapa de implementación no puede continuar: faltan campos obligatorios: {missing_fields}"
        ),

        # Provider Manager Errors (Fallback to English)
        MessageKey.NO_PROVIDERS_CONFIGURED: "Please add API keys in the Web Control Panel at {web_url}",
        MessageKey.ROLE_NOT_CONFIGURED: "Role '{role}' is not configured. Please configure it in the Web Control Panel at {web_url}",
        MessageKey.PROVIDER_UNAVAILABLE: "Provider '{provider}' for role '{role}' is not available. Please add an API key for {provider} in the Web Control Panel.",
        MessageKey.EXECUTION_MODE_NOT_CONFIGURED: "Execution mode not configured. Please choose and save it in the Web Control Panel ({web_url} -> Config -> Execution Mode).",
        MessageKey.UNSUPPORTED_MODEL: (
            "Modelo no compatible: '{model}'. Esta puerta de enlace Ternion solo admite 'ternion-team'. "
            "Si desea usar los modelos GPT/Claude/Gemini incluidos en la suscripción de Cursor, desactive "
            "\"OpenAI API Key\" y \"Override OpenAI Base URL\" en Configuración de Cursor "
            "(Configuración --> Modelos --> \"OpenAI API Key\" & \"Override OpenAI Base URL\"). "
            "Si desea usar Ternion, cambie el modelo a 'ternion-team'."
        ),
        MessageKey.NO_TERNION_ANALYSES_AVAILABLE: "No hay análisis de Ternion disponibles.",

        # Budget Alerts (Fallback to English)
        MessageKey.BUDGET_WARNING: (
            "\n> **[Ternion Budget Alert]**: Monthly usage has reached **{usage_pct}%**, "
            "approaching budget limit. This request may exceed monthly budget.\n"
            "> View usage details in Control Panel -> Usage page.\n\n"
        ),
        MessageKey.BUDGET_EXCEEDED: (
            "\n> **[Ternion Budget Exceeded]**: Monthly budget exhausted, request blocked.\n"
            "> Adjust budget settings in Control Panel -> Config page.\n\n"
        ),
        MessageKey.BUDGET_EXCEEDED_ERROR: "Monthly budget exhausted. Adjust budget in Control Panel -> Config page.",
        MessageKey.BUDGET_CONFIRM_REQUIRED: (
            "\n> **[Ternion Budget Alert]**: Monthly usage has reached **{usage_pct}%**. "
            "Reply with \"continue\" to proceed with the tool loop, or adjust budget settings "
            "in Control Panel -> Config page.\n"
        ),
        MessageKey.LOG_BUDGET_WARNING: "Budget warning | usage={usage_pct}% | Approaching monthly limit",
        MessageKey.LOG_BUDGET_EXCEEDED: "Budget exceeded | Request blocked | Monthly limit reached",
        MessageKey.LOG_BUDGET_IMPL_BLOCKED: "Budget exceeded | Implementation blocked | session_id={session_id}",
        MessageKey.LOG_BUDGET_CONFIRM_REQUIRED: "Budget warning | confirmation required | usage={usage_pct}%",

        # Tool Loop Guardrails
        MessageKey.TOOL_LOOP_FAILSAFE_REACHED: (
            "\n> **[Ternion]**: Tool loop reached the failsafe limit ({max_rounds}). "
            "Please narrow scope or provide exact file paths/line ranges, then start a new request.\n"
        ),
        MessageKey.LOG_TOOL_LOOP_FAILSAFE_REACHED: (
            "Tool loop failsafe reached | max_rounds={max_rounds} | session_id={session_id}"
        ),

        MessageKey.DELIVERABLE_POLICY_BLOCKED: (
            "[Ternion] La política de entregables bloqueó las llamadas de herramientas de escritura.\n"
            "Tipo de entregable: {deliverable_type}\n"
            "Alcance de escritura permitido: {allowed_scope}\n"
            "Objetivos bloqueados:\n{blocked_targets}\n"
            "Nota: Los destinos de escritura deben estar dentro de la raíz del proyecto y dentro del alcance permitido.\n"
        ),
        MessageKey.EXECUTION_TOOL_POLICY_BLOCKED: (
            "[Ternion] La política de herramientas bloqueó llamadas de Execution/Optimizer.\n"
            "Herramientas bloqueadas:\n{blocked_tools}\n"
            "Comandos de Shell bloqueados:\n{blocked_shell}\n"
        ),
        MessageKey.EVIDENCE_TOPUP_FINAL_REQUIRED: (
            "[Ternion] Solicitud de ampliación de evidencias rechazada: la 2.ª solicitud debe marcarse como final.\n"
            "Vuelva a emitir la solicitud con FINAL_REQUEST: true.\n"
        ),
        MessageKey.EVIDENCE_TOPUP_LIMIT_REACHED: (
            "[Ternion] Se alcanzó el límite de ampliación de evidencias ({max_rounds}). No se permiten más solicitudes de evidencias.\n"
            "Continúe con el entregable usando las evidencias existentes.\n"
        ),
        MessageKey.EVIDENCE_TOPUP_REQUESTS_EMPTY: (
            "[Ternion] Solicitud de ampliación de evidencias rechazada: el bloque de solicitudes no contiene solicitudes de evidencias accionables.\n"
            "Proporcione al menos una línea de solicitud y una línea PURPOSE por cada solicitud.\n"
        ),
        MessageKey.EVIDENCE_TOPUP_PURPOSE_REQUIRED: (
            "[Ternion] Solicitud de ampliación de evidencias rechazada: cada solicitud debe incluir una línea PURPOSE.\n"
            "Falta PURPOSE para:\n{missing_items}\n"
        ),

        # Discussion Output (Cursor-facing UI text)
        MessageKey.DISCUSSION_NO_OUTPUT: "[Ternion] La discusión finalizó pero no se generó ninguna salida.",
        MessageKey.DISCUSSION_ERRORS_HEADER: "[Ternion] Errores:\n",
        MessageKey.STREAM_ERROR_GENERIC: "\n\n[Ternion] Se produjo un error de streaming. Por favor, inténtalo de nuevo.\n",
        MessageKey.STREAM_ERROR_INTERRUPTED: "\n\n[Ternion] El streaming se interrumpió. Por favor, inténtalo de nuevo.\n",

        # Report Display (Cursor-facing UI text)
        MessageKey.REPORT_SECTION_ROOT_CAUSE_TITLE: "Causa raíz",
        MessageKey.REPORT_SECTION_EVIDENCE_TITLE: "Evidencia / Registros",
        MessageKey.REPORT_SECTION_SCOPE_TITLE: "Alcance y No-objetivos",
        MessageKey.REPORT_SECTION_FIX_PLAN_TITLE: "Plan de corrección / Recomendación",
        MessageKey.REPORT_SECTION_VERIFICATION_TITLE: "Verificación",
        MessageKey.REPORT_SECTION_RISKS_TITLE: "Riesgos y Reversión",
        MessageKey.REPORT_SECTION_IF_NOT_EFFECTIVE_TITLE: "Si no es efectivo, ¿y ahora qué?",
        MessageKey.REPORT_SECTION_MISSING_PLACEHOLDER: "(Falta)",
        MessageKey.REPORT_RAW_SESSION_NOTE: "El informe Markdown original se guarda en la sesión local: {path} (campo: {field})",
        MessageKey.EXECUTION_MODE_DESC_TERNION_FULL: "implementación de código por Ternion",
        MessageKey.EXECUTION_MODE_DESC_CURSOR_HANDOFF: "entrega de implementación a Cursor",
        MessageKey.REPORT_CONFIRM_PROMPT: (
            "Por favor revise el análisis anterior. Si es correcto, responda con su confirmación para continuar con {mode_desc}.\n"
            "Si no está de acuerdo o necesita ajustes, describa los problemas y volveré a analizar."
        ),
        MessageKey.REPORT_CONFIRM_PROMPT_CURSOR_HANDOFF: (
            "Está utilizando el modo \"Análisis de Causa Raíz de Ternion + Implementación de Cursor\". "
            "Por favor revise el análisis anterior. Si es correcto, vaya a Configuración de Cursor, desactive el interruptor \"OpenAI API Key\", "
            "seleccione un modelo nativo de Cursor (Gemini, Claude o serie GPT), luego responda con su confirmación para proceder "
            "con la entrega de implementación a Cursor.\n"
            "Si no está de acuerdo o necesita ajustes, describa los problemas y volveré a analizar."
        ),
    },
    "fr": {
        # Evidence Stage Errors
        MessageKey.EVIDENCE_COLLECTION_FAILED: "La collecte de preuves a échoué : {error}",
        MessageKey.REPORT_EVIDENCE_COLLECTION_FAILED: "La collecte de preuves pour le rapport a échoué : {error}",

        MessageKey.DIVERGENCE_START: "> **[Arbitre]**: Démarrage de l'analyse parallèle du problème...\n",
        MessageKey.DIVERGENCE_ANALYSIS: "> **[{ternion_id}]**: {preview}\n",
        MessageKey.DIVERGENCE_ANALYSIS_FAILED: "> **[{ternion_id}]**: L'analyse a échoué ({provider}) : {error}\n",
        MessageKey.CONVERGENCE_START: "> **[Arbitre]**: Synthèse des opinions, génération du rapport...\n",
        MessageKey.CONVERGENCE_COMPLETE: "> **[Arbitre]**: Rapport complet : {preview}\n",
        MessageKey.CONVERGENCE_ERROR: "> **[Arbitre]**: Erreur pendant la convergence : {error}\n",
        MessageKey.CONVERGENCE_ALL_ARBITERS_FAILED: "Tous les Arbitres ont échoué ; utilisation de l'analyse brute.",
        MessageKey.EXECUTION_START: "> **[Rédacteur]**: Génération du code à partir du rapport d'analyse...\n",
        MessageKey.EXECUTION_COMPLETE: "> **[Rédacteur]**: Génération de code terminée\n",
        MessageKey.EXECUTION_ERROR: "> **[Rédacteur]**: Erreur pendant l'exécution : {error}\n",
        MessageKey.OPTIMIZER_START: "> **[Optimiseur]**: Validation et amélioration de l’implémentation...\n",
        MessageKey.OPTIMIZER_OUTPUT_PROTOCOL_ERROR: (
            "\n[Ternion] Erreur de protocole de sortie de l’optimiseur : bloc de résumé utilisateur manquant. "
            "Le rapport interne de l’optimiseur a été capturé. Veuillez réessayer.\n"
        ),
        MessageKey.REVIEW_START: "> **[Réviseur]**: Vérification de la sécurité et de la logique du code...\n",
        MessageKey.REVIEW_APPROVED: "> **[Réviseur]**: Révision approuvée\n",
        MessageKey.REVIEW_REVISION: "> **[Réviseur]**: Révision nécessaire, retour à Rédacteur...\n",
        MessageKey.FINAL_CHECK_ERROR: "> **[Réviseur]**: Erreur pendant la révision : {error}\n",

        # Convergence Fallback
        MessageKey.CONVERGENCE_FALLBACK_WARNING: (
            "> **Note**: Ce rapport a été généré en utilisant une seule analyse (mode de repli) "
            "car la synthèse de l'Arbitre a échoué. L'analyse peut être moins complète que d'habitude."
        ),
        MessageKey.CONVERGENCE_FALLBACK_CONFIRM: (
            "Veuillez examiner l'analyse ci-dessus. Si elle est correcte, répondez avec votre confirmation pour procéder au transfert d'implémentation vers Cursor.\n"
            "Si vous n'êtes pas d'accord ou avez besoin d'ajustements, décrivez les problèmes et je réanalyserai."
        ),

        # Validation Errors
        MessageKey.EXECUTION_MODE_MISSING: (
            "Mode d'exécution non configuré. Veuillez ouvrir le Panneau de Contrôle Web : "
            "{web_url} (Config -> Mode d'Exécution -> Enregistrer)"
        ),
        MessageKey.ROLE_CONFIG_INCOMPLETE: (
            "Configuration du modèle de rôle incomplète. Veuillez configurer : {missing_roles}. "
            "Ouvrez le Panneau de Contrôle Web : {web_url}"
        ),
        MessageKey.EXECUTION_REQUIRES_AGENT_MODE: (
            "Cette requête est dans un mode Cursor non-Agent (Ask/Plan/Debug). "
            "L’exécution nécessite le mode Agent. Passez en Agent et confirmez à nouveau."
        ),
        MessageKey.IMPLEMENTATION_STAGE_MISSING_FIELDS: (
            "[Ternion] L’étape d’implémentation ne peut pas continuer : champs requis manquants : {missing_fields}"
        ),

        # Provider Manager Errors (Fallback to English)
        MessageKey.NO_PROVIDERS_CONFIGURED: "Please add API keys in the Web Control Panel at {web_url}",
        MessageKey.ROLE_NOT_CONFIGURED: "Role '{role}' is not configured. Please configure it in the Web Control Panel at {web_url}",
        MessageKey.PROVIDER_UNAVAILABLE: "Provider '{provider}' for role '{role}' is not available. Please add an API key for {provider} in the Web Control Panel.",
        MessageKey.EXECUTION_MODE_NOT_CONFIGURED: "Execution mode not configured. Please choose and save it in the Web Control Panel ({web_url} -> Config -> Execution Mode).",
        MessageKey.UNSUPPORTED_MODEL: (
            "Modèle non pris en charge : '{model}'. Cette passerelle Ternion ne prend en charge que 'ternion-team'. "
            "Si vous souhaitez utiliser les modèles GPT/Claude/Gemini inclus dans l'abonnement Cursor, veuillez désactiver "
            "\"OpenAI API Key\" et \"Override OpenAI Base URL\" dans les paramètres de Cursor "
            "(Paramètres --> Modèles --> \"OpenAI API Key\" & \"Override OpenAI Base URL\"). "
            "Si vous souhaitez utiliser Ternion, basculez vers le modèle 'ternion-team'."
        ),
        MessageKey.NO_TERNION_ANALYSES_AVAILABLE: "Aucune analyse Ternion disponible.",

        # Budget Alerts (Fallback to English)
        MessageKey.BUDGET_WARNING: (
            "\n> **[Ternion Budget Alert]**: Monthly usage has reached **{usage_pct}%**, "
            "approaching budget limit. This request may exceed monthly budget.\n"
            "> View usage details in Control Panel -> Usage page.\n\n"
        ),
        MessageKey.BUDGET_EXCEEDED: (
            "\n> **[Ternion Budget Exceeded]**: Monthly budget exhausted, request blocked.\n"
            "> Adjust budget settings in Control Panel -> Config page.\n\n"
        ),
        MessageKey.BUDGET_EXCEEDED_ERROR: "Monthly budget exhausted. Adjust budget in Control Panel -> Config page.",
        MessageKey.BUDGET_CONFIRM_REQUIRED: (
            "\n> **[Ternion Budget Alert]**: Monthly usage has reached **{usage_pct}%**. "
            "Reply with \"continue\" to proceed with the tool loop, or adjust budget settings "
            "in Control Panel -> Config page.\n"
        ),
        MessageKey.LOG_BUDGET_WARNING: "Budget warning | usage={usage_pct}% | Approaching monthly limit",
        MessageKey.LOG_BUDGET_EXCEEDED: "Budget exceeded | Request blocked | Monthly limit reached",
        MessageKey.LOG_BUDGET_IMPL_BLOCKED: "Budget exceeded | Implementation blocked | session_id={session_id}",
        MessageKey.LOG_BUDGET_CONFIRM_REQUIRED: "Budget warning | confirmation required | usage={usage_pct}%",

        # Tool Loop Guardrails
        MessageKey.TOOL_LOOP_FAILSAFE_REACHED: (
            "\n> **[Ternion]**: Tool loop reached the failsafe limit ({max_rounds}). "
            "Please narrow scope or provide exact file paths/line ranges, then start a new request.\n"
        ),
        MessageKey.LOG_TOOL_LOOP_FAILSAFE_REACHED: (
            "Tool loop failsafe reached | max_rounds={max_rounds} | session_id={session_id}"
        ),

        MessageKey.DELIVERABLE_POLICY_BLOCKED: (
            "[Ternion] La politique de livrables a bloqué les appels d’outils de modification.\n"
            "Type de livrable : {deliverable_type}\n"
            "Portée d’écriture autorisée : {allowed_scope}\n"
            "Cibles bloquées :\n{blocked_targets}\n"
            "Remarque : les cibles de modification doivent se trouver dans la racine du projet et dans la portée d’écriture autorisée.\n"
        ),
        MessageKey.EXECUTION_TOOL_POLICY_BLOCKED: (
            "[Ternion] La politique d’outils a bloqué des appels Execution/Optimizer.\n"
            "Outils bloqués :\n{blocked_tools}\n"
            "Commandes Shell bloquées :\n{blocked_shell}\n"
        ),
        MessageKey.EVIDENCE_TOPUP_FINAL_REQUIRED: (
            "[Ternion] Demande de complément de preuves rejetée : la 2e demande doit être marquée comme la dernière.\n"
            "Veuillez réémettre la demande avec FINAL_REQUEST: true.\n"
        ),
        MessageKey.EVIDENCE_TOPUP_LIMIT_REACHED: (
            "[Ternion] Limite de complément de preuves atteinte ({max_rounds}). Aucune autre demande de preuves n’est autorisée.\n"
            "Veuillez poursuivre le livrable avec les preuves existantes.\n"
        ),
        MessageKey.EVIDENCE_TOPUP_REQUESTS_EMPTY: (
            "[Ternion] Demande de complément de preuves rejetée : le bloc de demandes ne contient aucune demande de preuve exploitable.\n"
            "Veuillez fournir au moins une ligne de demande et une ligne PURPOSE pour chaque demande.\n"
        ),
        MessageKey.EVIDENCE_TOPUP_PURPOSE_REQUIRED: (
            "[Ternion] Demande de complément de preuves rejetée : chaque demande doit inclure une ligne PURPOSE.\n"
            "PURPOSE manquant pour :\n{missing_items}\n"
        ),

        # Discussion Output (Cursor-facing UI text)
        MessageKey.DISCUSSION_NO_OUTPUT: "[Ternion] La discussion est terminée mais aucune sortie n’a été générée.",
        MessageKey.DISCUSSION_ERRORS_HEADER: "[Ternion] Erreurs :\n",
        MessageKey.STREAM_ERROR_GENERIC: "\n\n[Ternion] Une erreur de streaming s’est produite. Veuillez réessayer.\n",
        MessageKey.STREAM_ERROR_INTERRUPTED: "\n\n[Ternion] Le streaming a été interrompu. Veuillez réessayer.\n",

        # Report Display (Cursor-facing UI text)
        MessageKey.REPORT_SECTION_ROOT_CAUSE_TITLE: "Cause racine",
        MessageKey.REPORT_SECTION_EVIDENCE_TITLE: "Preuves / Logs",
        MessageKey.REPORT_SECTION_SCOPE_TITLE: "Périmètre et Hors périmètre",
        MessageKey.REPORT_SECTION_FIX_PLAN_TITLE: "Plan de correction / Recommandation",
        MessageKey.REPORT_SECTION_VERIFICATION_TITLE: "Vérification",
        MessageKey.REPORT_SECTION_RISKS_TITLE: "Risques et Retour arrière",
        MessageKey.REPORT_SECTION_IF_NOT_EFFECTIVE_TITLE: "Si ce n’est pas efficace, ensuite ?",
        MessageKey.REPORT_SECTION_MISSING_PLACEHOLDER: "(Manquant)",
        MessageKey.REPORT_RAW_SESSION_NOTE: "Le rapport Markdown original est stocké dans la session locale : {path} (champ : {field})",
        MessageKey.EXECUTION_MODE_DESC_TERNION_FULL: "implémentation du code par Ternion",
        MessageKey.EXECUTION_MODE_DESC_CURSOR_HANDOFF: "transfert d’implémentation vers Cursor",
        MessageKey.REPORT_CONFIRM_PROMPT: (
            "Veuillez examiner l’analyse ci-dessus. Si elle est correcte, répondez avec votre confirmation pour continuer avec {mode_desc}.\n"
            "Si vous n’êtes pas d’accord ou avez besoin d’ajustements, décrivez les problèmes et je réanalyserai."
        ),
        MessageKey.REPORT_CONFIRM_PROMPT_CURSOR_HANDOFF: (
            "Vous utilisez le mode \"Analyse de Cause Racine Ternion + Implémentation Cursor\". "
            "Veuillez examiner l'analyse ci-dessus. Si elle est correcte, allez dans Paramètres Cursor, désactivez l'option \"OpenAI API Key\", "
            "sélectionnez un modèle natif Cursor (Gemini, Claude ou série GPT), puis répondez avec votre confirmation pour procéder "
            "au transfert d'implémentation vers Cursor.\n"
            "Si vous n'êtes pas d'accord ou avez besoin d'ajustements, décrivez les problèmes et je réanalyserai."
        ),
    },
    "de": {
        # Evidence Stage Errors
        MessageKey.EVIDENCE_COLLECTION_FAILED: "Beweissammlung fehlgeschlagen: {error}",
        MessageKey.REPORT_EVIDENCE_COLLECTION_FAILED: "Beweissammlung für den Bericht fehlgeschlagen: {error}",

        MessageKey.DIVERGENCE_START: "> **[Schiedsrichter]**: Starte parallele Problemanalyse...\n",
        MessageKey.DIVERGENCE_ANALYSIS: "> **[{ternion_id}]**: {preview}\n",
        MessageKey.DIVERGENCE_ANALYSIS_FAILED: "> **[{ternion_id}]**: Analyse fehlgeschlagen ({provider}): {error}\n",
        MessageKey.CONVERGENCE_START: "> **[Schiedsrichter]**: Meinungen synthetisieren, Bericht erstellen...\n",
        MessageKey.CONVERGENCE_COMPLETE: "> **[Schiedsrichter]**: Bericht fertig: {preview}\n",
        MessageKey.CONVERGENCE_ERROR: "> **[Schiedsrichter]**: Fehler bei der Konvergenz: {error}\n",
        MessageKey.CONVERGENCE_ALL_ARBITERS_FAILED: "Alle Arbiter sind fehlgeschlagen; es wird die Roh-Analyse verwendet.",
        MessageKey.EXECUTION_START: "> **[Verfasser]**: Code aus Analysebericht generieren...\n",
        MessageKey.EXECUTION_COMPLETE: "> **[Verfasser]**: Code-Generierung abgeschlossen\n",
        MessageKey.EXECUTION_ERROR: "> **[Verfasser]**: Fehler bei der Ausführung: {error}\n",
        MessageKey.OPTIMIZER_START: "> **[Optimierer]**: Implementierung prüfen und verbessern...\n",
        MessageKey.OPTIMIZER_OUTPUT_PROTOCOL_ERROR: (
            "\n[Ternion] Protokollfehler in der Optimizer-Ausgabe: Benutzer-Zusammenfassungsblock fehlt. "
            "Der interne Optimizer-Report wurde erfasst. Bitte erneut versuchen.\n"
        ),
        MessageKey.REVIEW_START: "> **[Prüfer]**: Code-Sicherheit und Logik überprüfen...\n",
        MessageKey.REVIEW_APPROVED: "> **[Prüfer]**: Überprüfung bestanden\n",
        MessageKey.REVIEW_REVISION: "> **[Prüfer]**: Revision erforderlich, zurück zu Verfasser...\n",
        MessageKey.FINAL_CHECK_ERROR: "> **[Prüfer]**: Fehler bei der Überprüfung: {error}\n",

        # Convergence Fallback
        MessageKey.CONVERGENCE_FALLBACK_WARNING: (
            "> **Hinweis**: Dieser Bericht wurde mit einer einzelnen Analyse (Fallback-Modus) erstellt, "
            "da die Synthese des Schiedsrichters fehlgeschlagen ist. Die Analyse ist möglicherweise weniger umfassend als üblich."
        ),
        MessageKey.CONVERGENCE_FALLBACK_CONFIRM: (
            "Bitte überprüfen Sie die obige Analyse. Wenn sie korrekt ist, antworten Sie mit Ihrer Bestätigung, um mit der Implementierungsübergabe an Cursor fortzufahren.\n"
            "Wenn Sie nicht einverstanden sind oder Anpassungen benötigen, beschreiben Sie die Probleme und ich werde neu analysieren."
        ),

        # Validation Errors
        MessageKey.EXECUTION_MODE_MISSING: (
            "Ausführungsmodus nicht konfiguriert. Bitte öffnen Sie das Web-Kontrollfeld: "
            "{web_url} (Konfiguration -> Ausführungsmodus -> Speichern)"
        ),
        MessageKey.ROLE_CONFIG_INCOMPLETE: (
            "Rollenmodell-Konfiguration unvollständig. Bitte konfigurieren: {missing_roles}. "
            "Öffnen Sie das Web-Kontrollfeld: {web_url}"
        ),
        MessageKey.EXECUTION_REQUIRES_AGENT_MODE: (
            "Diese Anfrage ist in einem nicht-Agent Cursor-Modus (Ask/Plan/Debug). "
            "Die Ausführung erfordert den Agent-Modus. Bitte zu Agent wechseln und erneut bestätigen."
        ),
        MessageKey.IMPLEMENTATION_STAGE_MISSING_FIELDS: (
            "[Ternion] Implementierungsphase kann nicht fortfahren: erforderliche Felder fehlen: {missing_fields}"
        ),

        # Provider Manager Errors (Fallback to English)
        MessageKey.NO_PROVIDERS_CONFIGURED: "Please add API keys in the Web Control Panel at {web_url}",
        MessageKey.ROLE_NOT_CONFIGURED: "Role '{role}' is not configured. Please configure it in the Web Control Panel at {web_url}",
        MessageKey.PROVIDER_UNAVAILABLE: "Provider '{provider}' for role '{role}' is not available. Please add an API key for {provider} in the Web Control Panel.",
        MessageKey.EXECUTION_MODE_NOT_CONFIGURED: "Execution mode not configured. Please choose and save it in the Web Control Panel ({web_url} -> Config -> Execution Mode).",
        MessageKey.UNSUPPORTED_MODEL: (
            "Nicht unterstütztes Modell: '{model}'. Dieses Ternion-Gateway unterstützt nur 'ternion-team'. "
            "Wenn Sie die in Cursor enthaltenen GPT/Claude/Gemini-Modelle verwenden möchten, deaktivieren Sie bitte "
            "\"OpenAI API Key\" und \"Override OpenAI Base URL\" in den Cursor-Einstellungen "
            "(Einstellungen --> Modelle --> \"OpenAI API Key\" & \"Override OpenAI Base URL\"). "
            "Wenn Sie Ternion verwenden möchten, wechseln Sie zum Modell 'ternion-team'."
        ),
        MessageKey.NO_TERNION_ANALYSES_AVAILABLE: "Keine Ternion-Analysen verfügbar.",

        # Budget Alerts (Fallback to English)
        MessageKey.BUDGET_WARNING: (
            "\n> **[Ternion Budget Alert]**: Monthly usage has reached **{usage_pct}%**, "
            "approaching budget limit. This request may exceed monthly budget.\n"
            "> View usage details in Control Panel -> Usage page.\n\n"
        ),
        MessageKey.BUDGET_EXCEEDED: (
            "\n> **[Ternion Budget Exceeded]**: Monthly budget exhausted, request blocked.\n"
            "> Adjust budget settings in Control Panel -> Config page.\n\n"
        ),
        MessageKey.BUDGET_EXCEEDED_ERROR: "Monthly budget exhausted. Adjust budget in Control Panel -> Config page.",
        MessageKey.BUDGET_CONFIRM_REQUIRED: (
            "\n> **[Ternion Budget Alert]**: Monthly usage has reached **{usage_pct}%**. "
            "Reply with \"continue\" to proceed with the tool loop, or adjust budget settings "
            "in Control Panel -> Config page.\n"
        ),
        MessageKey.LOG_BUDGET_WARNING: "Budget warning | usage={usage_pct}% | Approaching monthly limit",
        MessageKey.LOG_BUDGET_EXCEEDED: "Budget exceeded | Request blocked | Monthly limit reached",
        MessageKey.LOG_BUDGET_IMPL_BLOCKED: "Budget exceeded | Implementation blocked | session_id={session_id}",
        MessageKey.LOG_BUDGET_CONFIRM_REQUIRED: "Budget warning | confirmation required | usage={usage_pct}%",

        # Tool Loop Guardrails
        MessageKey.TOOL_LOOP_FAILSAFE_REACHED: (
            "\n> **[Ternion]**: Tool loop reached the failsafe limit ({max_rounds}). "
            "Please narrow scope or provide exact file paths/line ranges, then start a new request.\n"
        ),
        MessageKey.LOG_TOOL_LOOP_FAILSAFE_REACHED: (
            "Tool loop failsafe reached | max_rounds={max_rounds} | session_id={session_id}"
        ),

        MessageKey.DELIVERABLE_POLICY_BLOCKED: (
            "[Ternion] Die Deliverable-Policy hat Schreib-Tool-Aufrufe blockiert.\n"
            "Lieferobjekt-Typ: {deliverable_type}\n"
            "Erlaubter Schreibbereich: {allowed_scope}\n"
            "Blockierte Ziele:\n{blocked_targets}\n"
            "Hinweis: Änderungsziele müssen innerhalb des Projekt-Root und innerhalb des erlaubten Schreibbereichs liegen.\n"
        ),
        MessageKey.EXECUTION_TOOL_POLICY_BLOCKED: (
            "[Ternion] Die Tool-Policy hat Execution/Optimizer-Aufrufe blockiert.\n"
            "Blockierte Tools:\n{blocked_tools}\n"
            "Blockierte Shell-Befehle:\n{blocked_shell}\n"
        ),
        MessageKey.EVIDENCE_TOPUP_FINAL_REQUIRED: (
            "[Ternion] Beweis-Nachforderung abgelehnt: Die 2. Anfrage muss als letzte Anfrage markiert sein.\n"
            "Bitte senden Sie die Anfrage erneut mit FINAL_REQUEST: true.\n"
        ),
        MessageKey.EVIDENCE_TOPUP_LIMIT_REACHED: (
            "[Ternion] Limit für Beweis-Nachforderungen erreicht ({max_rounds}). Weitere Beweis-Anfragen sind nicht erlaubt.\n"
            "Bitte fahren Sie mit dem Deliverable anhand der vorhandenen Beweise fort.\n"
        ),
        MessageKey.EVIDENCE_TOPUP_REQUESTS_EMPTY: (
            "[Ternion] Beweis-Nachforderung abgelehnt: Der Anfrageblock enthält keine ausführbaren Beweisanfragen.\n"
            "Bitte geben Sie mindestens eine Anfragezeile und eine PURPOSE-Zeile pro Anfrage an.\n"
        ),
        MessageKey.EVIDENCE_TOPUP_PURPOSE_REQUIRED: (
            "[Ternion] Beweis-Nachforderung abgelehnt: Jede Anfrage muss eine PURPOSE-Zeile enthalten.\n"
            "Fehlendes PURPOSE für:\n{missing_items}\n"
        ),

        # Discussion Output (Cursor-facing UI text)
        MessageKey.DISCUSSION_NO_OUTPUT: "[Ternion] Die Diskussion ist abgeschlossen, aber es wurde keine Ausgabe erzeugt.",
        MessageKey.DISCUSSION_ERRORS_HEADER: "[Ternion] Fehler:\n",
        MessageKey.STREAM_ERROR_GENERIC: "\n\n[Ternion] Beim Streaming ist ein Fehler aufgetreten. Bitte erneut versuchen.\n",
        MessageKey.STREAM_ERROR_INTERRUPTED: "\n\n[Ternion] Das Streaming wurde unterbrochen. Bitte erneut versuchen.\n",

        # Report Display (Cursor-facing UI text)
        MessageKey.REPORT_SECTION_ROOT_CAUSE_TITLE: "Ursache",
        MessageKey.REPORT_SECTION_EVIDENCE_TITLE: "Evidenz / Logs",
        MessageKey.REPORT_SECTION_SCOPE_TITLE: "Umfang & Nicht-Ziele",
        MessageKey.REPORT_SECTION_FIX_PLAN_TITLE: "Fix-Plan / Empfehlung",
        MessageKey.REPORT_SECTION_VERIFICATION_TITLE: "Verifizierung",
        MessageKey.REPORT_SECTION_RISKS_TITLE: "Risiken & Rollback",
        MessageKey.REPORT_SECTION_IF_NOT_EFFECTIVE_TITLE: "Falls nicht wirksam, was dann?",
        MessageKey.REPORT_SECTION_MISSING_PLACEHOLDER: "(Fehlt)",
        MessageKey.REPORT_RAW_SESSION_NOTE: "Der ursprüngliche Markdown-Bericht ist in der lokalen Session gespeichert: {path} (Feld: {field})",
        MessageKey.EXECUTION_MODE_DESC_TERNION_FULL: "Code-Implementierung durch Ternion",
        MessageKey.EXECUTION_MODE_DESC_CURSOR_HANDOFF: "Übergabe der Implementierung an Cursor",
        MessageKey.REPORT_CONFIRM_PROMPT: (
            "Bitte prüfen Sie die Analyse oben. Wenn sie korrekt ist, antworten Sie mit Ihrer Bestätigung, um mit {mode_desc} fortzufahren.\n"
            "Wenn Sie nicht einverstanden sind oder Anpassungen benötigen, beschreiben Sie die Probleme und ich werde neu analysieren."
        ),
        MessageKey.REPORT_CONFIRM_PROMPT_CURSOR_HANDOFF: (
            "Sie verwenden den Modus \"Ternion Ursachenanalyse + Cursor Implementierung\". "
            "Bitte prüfen Sie die Analyse oben. Wenn sie korrekt ist, gehen Sie zu Cursor-Einstellungen, deaktivieren Sie den \"OpenAI API Key\"-Schalter, "
            "wählen Sie ein natives Cursor-Modell (Gemini, Claude oder GPT-Serie), dann antworten Sie mit Ihrer Bestätigung, um mit der "
            "Übergabe der Implementierung an Cursor fortzufahren.\n"
            "Wenn Sie nicht einverstanden sind oder Anpassungen benötigen, beschreiben Sie die Probleme und ich werde neu analysieren."
        ),
    },
    "ja": {
        # Evidence Stage Errors
        MessageKey.EVIDENCE_COLLECTION_FAILED: "証拠収集に失敗しました: {error}",
        MessageKey.REPORT_EVIDENCE_COLLECTION_FAILED: "レポート段階の証拠補完に失敗しました: {error}",

        MessageKey.DIVERGENCE_START: "> **[調停者]**: 並列問題分析を開始...\n",
        MessageKey.DIVERGENCE_ANALYSIS: "> **[{ternion_id}]**: {preview}\n",
        MessageKey.DIVERGENCE_ANALYSIS_FAILED: "> **[{ternion_id}]**: 分析に失敗しました（{provider}）：{error}\n",
        MessageKey.CONVERGENCE_START: "> **[調停者]**: 意見を統合し、レポートを作成中...\n",
        MessageKey.CONVERGENCE_COMPLETE: "> **[調停者]**: レポート完成: {preview}\n",
        MessageKey.CONVERGENCE_ERROR: "> **[調停者]**: 収束中にエラー: {error}\n",
        MessageKey.CONVERGENCE_ALL_ARBITERS_FAILED: "すべてのアービターが失敗したため、生の分析を使用します。",
        MessageKey.EXECUTION_START: "> **[執筆者]**: 分析レポートからコードを生成中...\n",
        MessageKey.EXECUTION_COMPLETE: "> **[執筆者]**: コード生成完了\n",
        MessageKey.EXECUTION_ERROR: "> **[執筆者]**: 実行中にエラー: {error}\n",
        MessageKey.OPTIMIZER_START: "> **[最適化担当]**: 受け入れ基準に基づき実装を検証・改善中...\n",
        MessageKey.OPTIMIZER_OUTPUT_PROTOCOL_ERROR: (
            "\n[Ternion] 最適化担当の出力プロトコルエラー：ユーザー向けサマリーブロックがありません。"
            "内部レポートは保存されました。再試行してください。\n"
        ),
        MessageKey.REVIEW_START: "> **[審査者]**: コードのセキュリティとロジックを確認中...\n",
        MessageKey.REVIEW_APPROVED: "> **[審査者]**: レビュー通過\n",
        MessageKey.REVIEW_REVISION: "> **[審査者]**: 修正が必要、執筆者に戻ります...\n",
        MessageKey.FINAL_CHECK_ERROR: "> **[審査者]**: レビュー中にエラー: {error}\n",

        # Convergence Fallback
        MessageKey.CONVERGENCE_FALLBACK_WARNING: (
            "> **注意**: このレポートは、調停者の統合が失敗したため、単一の分析（フォールバックモード）を使用して生成されました。"
            "分析は通常より包括的でない場合があります。"
        ),
        MessageKey.CONVERGENCE_FALLBACK_CONFIRM: (
            "上記の分析を確認してください。正しければ、確認の返信をしてCursorへの実装引き継ぎに進んでください。\n"
            "同意できない場合や調整が必要な場合は、問題を記述してください。再分析します。"
        ),

        # Validation Errors
        MessageKey.EXECUTION_MODE_MISSING: (
            "実行モードが設定されていません。Webコントロールパネルを開いて設定してください："
            "{web_url}（設定 -> 実行モード -> 保存）"
        ),
        MessageKey.ROLE_CONFIG_INCOMPLETE: (
            "ロールモデル設定が不完全です。設定が必要：{missing_roles}。"
            "Webコントロールパネルを開いてください：{web_url}"
        ),
        MessageKey.EXECUTION_REQUIRES_AGENT_MODE: (
            "このリクエストは Cursor の非 Agent モード（Ask/Plan/Debug）です。"
            "実行には Agent モードが必要です。Agent に切り替えてから再度確認してください。"
        ),
        MessageKey.IMPLEMENTATION_STAGE_MISSING_FIELDS: (
            "[Ternion] 実装ステージを続行できません：必須フィールドが不足しています：{missing_fields}"
        ),

        # Provider Manager Errors (Fallback to English)
        MessageKey.NO_PROVIDERS_CONFIGURED: "Please add API keys in the Web Control Panel at {web_url}",
        MessageKey.ROLE_NOT_CONFIGURED: "Role '{role}' is not configured. Please configure it in the Web Control Panel at {web_url}",
        MessageKey.PROVIDER_UNAVAILABLE: "Provider '{provider}' for role '{role}' is not available. Please add an API key for {provider} in the Web Control Panel.",
        MessageKey.EXECUTION_MODE_NOT_CONFIGURED: "Execution mode not configured. Please choose and save it in the Web Control Panel ({web_url} -> Config -> Execution Mode).",
        MessageKey.UNSUPPORTED_MODEL: (
            "サポートされていないモデル: '{model}'。このTernionゲートウェイは 'ternion-team' のみをサポートしています。"
            "Cursorサブスクリプションに含まれるGPT/Claude/Geminiモデルを使用する場合は、Cursor設定で "
            "\"OpenAI API Key\" と \"Override OpenAI Base URL\" を無効にしてください "
            "(設定 --> モデル --> \"OpenAI API Key\" & \"Override OpenAI Base URL\")。"
            "Ternionを使用する場合は、モデルを 'ternion-team' に切り替えてください。"
        ),
        MessageKey.NO_TERNION_ANALYSES_AVAILABLE: "利用可能なTernion分析がありません。",

        # Budget Alerts (Fallback to English)
        MessageKey.BUDGET_WARNING: (
            "\n> **[Ternion Budget Alert]**: Monthly usage has reached **{usage_pct}%**, "
            "approaching budget limit. This request may exceed monthly budget.\n"
            "> View usage details in Control Panel -> Usage page.\n\n"
        ),
        MessageKey.BUDGET_EXCEEDED: (
            "\n> **[Ternion Budget Exceeded]**: Monthly budget exhausted, request blocked.\n"
            "> Adjust budget settings in Control Panel -> Config page.\n\n"
        ),
        MessageKey.BUDGET_EXCEEDED_ERROR: "Monthly budget exhausted. Adjust budget in Control Panel -> Config page.",
        MessageKey.BUDGET_CONFIRM_REQUIRED: (
            "\n> **[Ternion Budget Alert]**: Monthly usage has reached **{usage_pct}%**. "
            "Reply with \"continue\" to proceed with the tool loop, or adjust budget settings "
            "in Control Panel -> Config page.\n"
        ),
        MessageKey.LOG_BUDGET_WARNING: "Budget warning | usage={usage_pct}% | Approaching monthly limit",
        MessageKey.LOG_BUDGET_EXCEEDED: "Budget exceeded | Request blocked | Monthly limit reached",
        MessageKey.LOG_BUDGET_IMPL_BLOCKED: "Budget exceeded | Implementation blocked | session_id={session_id}",
        MessageKey.LOG_BUDGET_CONFIRM_REQUIRED: "Budget warning | confirmation required | usage={usage_pct}%",

        # Tool Loop Guardrails
        MessageKey.TOOL_LOOP_FAILSAFE_REACHED: (
            "\n> **[Ternion]**: Tool loop reached the failsafe limit ({max_rounds}). "
            "Please narrow scope or provide exact file paths/line ranges, then start a new request.\n"
        ),
        MessageKey.LOG_TOOL_LOOP_FAILSAFE_REACHED: (
            "Tool loop failsafe reached | max_rounds={max_rounds} | session_id={session_id}"
        ),

        MessageKey.DELIVERABLE_POLICY_BLOCKED: (
            "[Ternion] 交付物ポリシーにより書き込みツール呼び出しがブロックされました。\n"
            "交付物タイプ: {deliverable_type}\n"
            "許可された書き込み範囲: {allowed_scope}\n"
            "ブロックされた対象:\n{blocked_targets}\n"
            "注意: 変更対象はプロジェクトルート内かつ許可された書き込み範囲内である必要があります。\n"
        ),
        MessageKey.EXECUTION_TOOL_POLICY_BLOCKED: (
            "[Ternion] ツールポリシーにより Execution/Optimizer の呼び出しがブロックされました。\n"
            "ブロックされたツール:\n{blocked_tools}\n"
            "ブロックされた Shell コマンド:\n{blocked_shell}\n"
        ),
        MessageKey.EVIDENCE_TOPUP_FINAL_REQUIRED: (
            "[Ternion] 証拠補完リクエストは拒否されました：2 回目のリクエストは最後のリクエストとして明示する必要があります。\n"
            "FINAL_REQUEST: true を設定して再リクエストしてください。\n"
        ),
        MessageKey.EVIDENCE_TOPUP_LIMIT_REACHED: (
            "[Ternion] 証拠補完の上限に達しました（{max_rounds}）。これ以上の証拠リクエストは許可されません。\n"
            "既存の証拠に基づいて Deliverable を継続してください。\n"
        ),
        MessageKey.EVIDENCE_TOPUP_REQUESTS_EMPTY: (
            "[Ternion] 証拠補完リクエストは拒否されました：リクエストブロックに実行可能な証拠リクエストが含まれていません。\n"
            "少なくとも 1 行のリクエストと、各リクエストに対して 1 行の PURPOSE を提供してください。\n"
        ),
        MessageKey.EVIDENCE_TOPUP_PURPOSE_REQUIRED: (
            "[Ternion] 証拠補完リクエストは拒否されました：各リクエストには PURPOSE 行が必要です。\n"
            "PURPOSE が欠落しているリクエスト:\n{missing_items}\n"
        ),

        # Discussion Output (Cursor-facing UI text)
        MessageKey.DISCUSSION_NO_OUTPUT: "[Ternion] ディスカッションは完了しましたが、出力が生成されませんでした。",
        MessageKey.DISCUSSION_ERRORS_HEADER: "[Ternion] エラー:\n",
        MessageKey.STREAM_ERROR_GENERIC: "\n\n[Ternion] ストリーミング中にエラーが発生しました。もう一度お試しください。\n",
        MessageKey.STREAM_ERROR_INTERRUPTED: "\n\n[Ternion] ストリーミングが中断されました。もう一度お試しください。\n",

        # Report Display (Cursor-facing UI text)
        MessageKey.REPORT_SECTION_ROOT_CAUSE_TITLE: "根本原因",
        MessageKey.REPORT_SECTION_EVIDENCE_TITLE: "証拠 / ログ",
        MessageKey.REPORT_SECTION_SCOPE_TITLE: "範囲と非目標",
        MessageKey.REPORT_SECTION_FIX_PLAN_TITLE: "修正計画 / 推奨",
        MessageKey.REPORT_SECTION_VERIFICATION_TITLE: "検証",
        MessageKey.REPORT_SECTION_RISKS_TITLE: "リスクとロールバック",
        MessageKey.REPORT_SECTION_IF_NOT_EFFECTIVE_TITLE: "効果がない場合、次は？",
        MessageKey.REPORT_SECTION_MISSING_PLACEHOLDER: "（欠落）",
        MessageKey.REPORT_RAW_SESSION_NOTE: "元の Markdown レポートはローカルセッションに保存されています: {path}（フィールド: {field}）",
        MessageKey.EXECUTION_MODE_DESC_TERNION_FULL: "Ternion によるコード実装",
        MessageKey.EXECUTION_MODE_DESC_CURSOR_HANDOFF: "Cursor への実装引き継ぎ",
        MessageKey.REPORT_CONFIRM_PROMPT: (
            "上記の分析を確認してください。正しければ、確認の返信をして {mode_desc} を続行してください。\n"
            "同意できない場合や調整が必要な場合は、問題を記述してください。再分析します。"
        ),
        MessageKey.REPORT_CONFIRM_PROMPT_CURSOR_HANDOFF: (
            "「Ternion 根本原因分析 + Cursor 実装」モードを使用しています。"
            "上記の分析を確認してください。正しければ、Cursor設定で「OpenAI API Key」スイッチをオフにし、"
            "Cursorネイティブモデル（Gemini、Claude、またはGPTシリーズ）を選択してから、確認の返信をして "
            "Cursorへの実装引き継ぎを続行してください。\n"
            "同意できない場合や調整が必要な場合は、問題を記述してください。再分析します。"
        ),
    },
    "ko": {
        # Evidence Stage Errors
        MessageKey.EVIDENCE_COLLECTION_FAILED: "증거 수집에 실패했습니다: {error}",
        MessageKey.REPORT_EVIDENCE_COLLECTION_FAILED: "보고서 단계 증거 보완에 실패했습니다: {error}",

        MessageKey.DIVERGENCE_START: "> **[중재자]**: 병렬 문제 분석 시작...\n",
        MessageKey.DIVERGENCE_ANALYSIS: "> **[{ternion_id}]**: {preview}\n",
        MessageKey.DIVERGENCE_ANALYSIS_FAILED: "> **[{ternion_id}]**: 분석 실패({provider}): {error}\n",
        MessageKey.CONVERGENCE_START: "> **[중재자]**: 의견 종합, 보고서 작성 중...\n",
        MessageKey.CONVERGENCE_COMPLETE: "> **[중재자]**: 보고서 완성: {preview}\n",
        MessageKey.CONVERGENCE_ERROR: "> **[중재자]**: 수렴 중 오류: {error}\n",
        MessageKey.CONVERGENCE_ALL_ARBITERS_FAILED: "모든 Arbiter가 실패하여 원본 분석을 사용합니다.",
        MessageKey.EXECUTION_START: "> **[작성자]**: 분석 보고서에서 코드 생성 중...\n",
        MessageKey.EXECUTION_COMPLETE: "> **[작성자]**: 코드 생성 완료\n",
        MessageKey.EXECUTION_ERROR: "> **[작성자]**: 실행 중 오류: {error}\n",
        MessageKey.OPTIMIZER_START: "> **[최적화 담당]**: 수용 기준에 따라 구현을 검증·개선 중...\n",
        MessageKey.OPTIMIZER_OUTPUT_PROTOCOL_ERROR: (
            "\n[Ternion] 최적화 출력 프로토콜 오류: 사용자 요약 블록이 누락되었습니다. "
            "내부 최적화 보고서는 캡처되었습니다. 다시 시도해 주세요.\n"
        ),
        MessageKey.REVIEW_START: "> **[검토자]**: 코드 보안 및 로직 검토 중...\n",
        MessageKey.REVIEW_APPROVED: "> **[검토자]**: 검토 통과\n",
        MessageKey.REVIEW_REVISION: "> **[검토자]**: 수정 필요, 작성자에게 돌아갑니다...\n",
        MessageKey.FINAL_CHECK_ERROR: "> **[검토자]**: 검토 중 오류: {error}\n",

        # Convergence Fallback
        MessageKey.CONVERGENCE_FALLBACK_WARNING: (
            "> **주의**: 이 보고서는 중재자 합성이 실패하여 단일 분석(폴백 모드)을 사용하여 생성되었습니다. "
            "분석이 평소보다 덜 포괄적일 수 있습니다."
        ),
        MessageKey.CONVERGENCE_FALLBACK_CONFIRM: (
            "위의 분석을 검토해 주세요. 올바르다면 확인 응답을 보내 Cursor로의 구현 인계를 진행하세요.\n"
            "동의하지 않거나 조정이 필요하면 문제를 설명해 주세요. 다시 분석하겠습니다."
        ),

        # Validation Errors
        MessageKey.EXECUTION_MODE_MISSING: (
            "실행 모드가 구성되지 않았습니다. 웹 제어판을 열어 구성하세요: "
            "{web_url} (설정 -> 실행 모드 -> 저장)"
        ),
        MessageKey.ROLE_CONFIG_INCOMPLETE: (
            "역할 모델 구성이 불완전합니다. 구성 필요: {missing_roles}. "
            "웹 제어판을 열어주세요: {web_url}"
        ),
        MessageKey.EXECUTION_REQUIRES_AGENT_MODE: (
            "이 요청은 Cursor의 비 Agent 모드(Ask/Plan/Debug)입니다. "
            "실행에는 Agent 모드가 필요합니다. Agent로 전환한 뒤 다시 확인해 주세요."
        ),
        MessageKey.IMPLEMENTATION_STAGE_MISSING_FIELDS: (
            "[Ternion] 구현 단계를 진행할 수 없습니다: 필수 필드가 누락되었습니다: {missing_fields}"
        ),

        # Provider Manager Errors (Fallback to English)
        MessageKey.NO_PROVIDERS_CONFIGURED: "Please add API keys in the Web Control Panel at {web_url}",
        MessageKey.ROLE_NOT_CONFIGURED: "Role '{role}' is not configured. Please configure it in the Web Control Panel at {web_url}",
        MessageKey.PROVIDER_UNAVAILABLE: "Provider '{provider}' for role '{role}' is not available. Please add an API key for {provider} in the Web Control Panel.",
        MessageKey.EXECUTION_MODE_NOT_CONFIGURED: "Execution mode not configured. Please choose and save it in the Web Control Panel ({web_url} -> Config -> Execution Mode).",
        MessageKey.UNSUPPORTED_MODEL: (
            "지원되지 않는 모델: '{model}'. 이 Ternion 게이트웨이는 'ternion-team'만 지원합니다. "
            "Cursor 구독에 포함된 GPT/Claude/Gemini 모델을 사용하려면 Cursor 설정에서 "
            "\"OpenAI API Key\" 및 \"Override OpenAI Base URL\"을 비활성화하세요 "
            "(설정 --> 모델 --> \"OpenAI API Key\" & \"Override OpenAI Base URL\"). "
            "Ternion을 사용하려면 모델을 'ternion-team'으로 전환하세요."
        ),
        MessageKey.NO_TERNION_ANALYSES_AVAILABLE: "사용 가능한 Ternion 분석이 없습니다.",

        # Budget Alerts (Fallback to English)
        MessageKey.BUDGET_WARNING: (
            "\n> **[Ternion Budget Alert]**: Monthly usage has reached **{usage_pct}%**, "
            "approaching budget limit. This request may exceed monthly budget.\n"
            "> View usage details in Control Panel -> Usage page.\n\n"
        ),
        MessageKey.BUDGET_EXCEEDED: (
            "\n> **[Ternion Budget Exceeded]**: Monthly budget exhausted, request blocked.\n"
            "> Adjust budget settings in Control Panel -> Config page.\n\n"
        ),
        MessageKey.BUDGET_EXCEEDED_ERROR: "Monthly budget exhausted. Adjust budget in Control Panel -> Config page.",
        MessageKey.BUDGET_CONFIRM_REQUIRED: (
            "\n> **[Ternion Budget Alert]**: Monthly usage has reached **{usage_pct}%**. "
            "Reply with \"continue\" to proceed with the tool loop, or adjust budget settings "
            "in Control Panel -> Config page.\n"
        ),
        MessageKey.LOG_BUDGET_WARNING: "Budget warning | usage={usage_pct}% | Approaching monthly limit",
        MessageKey.LOG_BUDGET_EXCEEDED: "Budget exceeded | Request blocked | Monthly limit reached",
        MessageKey.LOG_BUDGET_IMPL_BLOCKED: "Budget exceeded | Implementation blocked | session_id={session_id}",
        MessageKey.LOG_BUDGET_CONFIRM_REQUIRED: "Budget warning | confirmation required | usage={usage_pct}%",

        # Tool Loop Guardrails
        MessageKey.TOOL_LOOP_FAILSAFE_REACHED: (
            "\n> **[Ternion]**: Tool loop reached the failsafe limit ({max_rounds}). "
            "Please narrow scope or provide exact file paths/line ranges, then start a new request.\n"
        ),
        MessageKey.LOG_TOOL_LOOP_FAILSAFE_REACHED: (
            "Tool loop failsafe reached | max_rounds={max_rounds} | session_id={session_id}"
        ),

        MessageKey.DELIVERABLE_POLICY_BLOCKED: (
            "[Ternion] 전달물 정책으로 인해 쓰기 도구 호출이 차단되었습니다.\n"
            "전달물 유형: {deliverable_type}\n"
            "허용된 쓰기 범위: {allowed_scope}\n"
            "차단된 대상:\n{blocked_targets}\n"
            "참고: 변경 대상은 프로젝트 루트 내부이며 허용된 쓰기 범위 내여야 합니다.\n"
        ),
        MessageKey.EXECUTION_TOOL_POLICY_BLOCKED: (
            "[Ternion] 도구 정책으로 인해 Execution/Optimizer 호출이 차단되었습니다.\n"
            "차단된 도구:\n{blocked_tools}\n"
            "차단된 Shell 명령:\n{blocked_shell}\n"
        ),
        MessageKey.EVIDENCE_TOPUP_FINAL_REQUIRED: (
            "[Ternion] 증거 보완 요청이 거부되었습니다: 2번째 요청은 마지막 요청으로 명시되어야 합니다.\n"
            "FINAL_REQUEST: true 로 다시 요청해 주세요.\n"
        ),
        MessageKey.EVIDENCE_TOPUP_LIMIT_REACHED: (
            "[Ternion] 증거 보완 횟수 한도에 도달했습니다({max_rounds}). 추가 증거 요청은 허용되지 않습니다.\n"
            "기존 증거로 Deliverable 을 계속 진행해 주세요.\n"
        ),
        MessageKey.EVIDENCE_TOPUP_REQUESTS_EMPTY: (
            "[Ternion] 증거 보완 요청이 거부되었습니다: 요청 블록에 실행 가능한 증거 요청이 없습니다.\n"
            "각 요청마다 최소 1개의 요청 라인과 1개의 PURPOSE 라인을 제공해 주세요.\n"
        ),
        MessageKey.EVIDENCE_TOPUP_PURPOSE_REQUIRED: (
            "[Ternion] 증거 보완 요청이 거부되었습니다: 모든 요청에는 PURPOSE 라인이 필요합니다.\n"
            "PURPOSE 누락 항목:\n{missing_items}\n"
        ),

        # Discussion Output (Cursor-facing UI text)
        MessageKey.DISCUSSION_NO_OUTPUT: "[Ternion] 토론이 완료되었지만 출력이 생성되지 않았습니다.",
        MessageKey.DISCUSSION_ERRORS_HEADER: "[Ternion] 오류:\n",
        MessageKey.STREAM_ERROR_GENERIC: "\n\n[Ternion] 스트리밍 중 오류가 발생했습니다. 다시 시도해 주세요.\n",
        MessageKey.STREAM_ERROR_INTERRUPTED: "\n\n[Ternion] 스트리밍이 중단되었습니다. 다시 시도해 주세요.\n",

        # Report Display (Cursor-facing UI text)
        MessageKey.REPORT_SECTION_ROOT_CAUSE_TITLE: "근본 원인",
        MessageKey.REPORT_SECTION_EVIDENCE_TITLE: "증거 / 로그",
        MessageKey.REPORT_SECTION_SCOPE_TITLE: "범위 및 비목표",
        MessageKey.REPORT_SECTION_FIX_PLAN_TITLE: "수정 계획 / 권고",
        MessageKey.REPORT_SECTION_VERIFICATION_TITLE: "검증",
        MessageKey.REPORT_SECTION_RISKS_TITLE: "위험 및 롤백",
        MessageKey.REPORT_SECTION_IF_NOT_EFFECTIVE_TITLE: "효과가 없으면 다음은?",
        MessageKey.REPORT_SECTION_MISSING_PLACEHOLDER: "(누락)",
        MessageKey.REPORT_RAW_SESSION_NOTE: "원본 Markdown 보고서는 로컬 세션에 저장되어 있습니다: {path} (필드: {field})",
        MessageKey.EXECUTION_MODE_DESC_TERNION_FULL: "Ternion에 의한 코드 구현",
        MessageKey.EXECUTION_MODE_DESC_CURSOR_HANDOFF: "Cursor로 구현 인계",
        MessageKey.REPORT_CONFIRM_PROMPT: (
            "위의 분석을 검토해 주세요. 올바르다면 확인 응답을 보내 {mode_desc} 을(를) 진행하세요.\n"
            "동의하지 않거나 조정이 필요하면 문제를 설명해 주세요. 다시 분석하겠습니다."
        ),
        MessageKey.REPORT_CONFIRM_PROMPT_CURSOR_HANDOFF: (
            "\"Ternion 근본 원인 분석 + Cursor 구현\" 모드를 사용 중입니다. "
            "위의 분석을 검토해 주세요. 올바르다면 Cursor 설정에서 \"OpenAI API Key\" 스위치를 끄고, "
            "Cursor 네이티브 모델(Gemini, Claude 또는 GPT 시리즈)을 선택한 다음, 확인 응답을 보내 "
            "Cursor로 구현 인계를 진행하세요.\n"
            "동의하지 않거나 조정이 필요하면 문제를 설명해 주세요. 다시 분석하겠습니다."
        ),
    },
}

DEFAULT_LANGUAGE: Language = "en"


def get_web_base_url() -> str:
    """
    Get the Web Control Panel base URL dynamically from user config.
    """
    try:
        config = config_store.load()
        # access attribute directly or use getattr, ports is Pydantic model
        port = getattr(config.ports, "web", 9120)
    except Exception:
        port = 9120
    return f"http://localhost:{port}"


def get_user_language() -> Language:
    """Get user's preferred language from configuration."""
    try:
        config = config_store.load()
        lang = getattr(config, "language", DEFAULT_LANGUAGE)

        # Handle "auto" language setting - use browser_language
        if lang == "auto":
            browser_lang = getattr(config, "browser_language", DEFAULT_LANGUAGE)
            if browser_lang in ("en", "zh", "es", "fr", "de", "ja", "ko"):
                return browser_lang
            return DEFAULT_LANGUAGE

        if lang in ("en", "zh", "es", "fr", "de", "ja", "ko"):
            return lang
    except Exception:
        pass

    return DEFAULT_LANGUAGE


def t(key: MessageKey, **kwargs: str) -> str:
    """
    Get translated string for the given key.

    Args:
        key: Translation key from MessageKey enum
        **kwargs: Format arguments for string interpolation

    Returns:
        Translated and formatted string
    """
    lang = get_user_language()

    # Fallback to English if key missing in target language
    template = TRANSLATIONS.get(lang, {}).get(key)
    if not template:
        template = TRANSLATIONS[DEFAULT_LANGUAGE].get(key, str(key))

    # Inject Web URL if not provided
    if "{web_url}" in template and "web_url" not in kwargs:
        kwargs["web_url"] = get_web_base_url()

    try:
        return template.format(**kwargs)
    except KeyError:
        return template  # Return unformatted on error
