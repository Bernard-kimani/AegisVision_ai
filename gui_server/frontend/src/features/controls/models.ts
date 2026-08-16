// Ported from gui_server/gui/controls_tab.py::get_models_for_provider
// "openai" is the internal provider key (matches server/llm/create_provider's
// routing) but means "OpenAI-compatible" - Fireworks AI running Qwen2.5-VL /
// DeepSeek by default, not literally OpenAI's own API. Gemini stays wired as
// a configurable fallback.
export const MODELS_BY_PROVIDER: Record<string, { value: string; label: string }[]> = {
  openai: [
    { value: 'accounts/fireworks/models/qwen2p5-vl-32b-instruct', label: 'Qwen2.5-VL 32B (vision, default)' },
    { value: 'accounts/fireworks/models/deepseek-v3', label: 'DeepSeek-V3' },
  ],
  gemini: [
    { value: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash' },
    { value: 'gemini-2.5-flash-lite', label: 'Gemini 2.5 Flash Lite' },
    { value: 'gemini-2.0-flash-exp', label: 'Gemini 2.0 Flash (exp)' },
    { value: 'gemini-1.5-flash-latest', label: 'Gemini 1.5 Flash' },
    { value: 'gemini-1.5-pro-latest', label: 'Gemini 1.5 Pro' },
  ],
  anthropic: [
    { value: 'claude-3-5-sonnet-20241022', label: 'Claude 3.5 Sonnet' },
    { value: 'claude-3-opus-20240229', label: 'Claude 3 Opus' },
    { value: 'claude-3-haiku-20240307', label: 'Claude 3 Haiku' },
  ],
}

export const PROVIDER_LABELS: Record<string, string> = {
  openai: 'Fireworks AI (Qwen / DeepSeek)',
  gemini: 'Gemini (fallback)',
  anthropic: 'Anthropic',
}
