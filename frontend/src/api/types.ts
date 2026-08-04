export type AudioStatus = 'pending' | 'processing' | 'ready' | 'error'
export type SourceType = 'rss' | 'html' | 'auto'

export interface Columnist {
  id: number
  name: string
  outlet: string
  source_url: string
  feed_url: string | null
  source_type: SourceType
  expected_frequency: string
  extractor_key: string | null
  active: boolean
  notes: string | null
  consecutive_failures: number
  last_success_at: string | null
  last_error: string | null
  created_at: string
  article_count: number
  unread_count: number
}

export interface Block {
  type: 'p' | 'h2' | 'h3' | 'quote' | 'li'
  html: string
  text: string
}

export interface AudioMark {
  paragraph_index: number
  start: number
  end: number
}

export interface AudioInfo {
  id: number
  status: AudioStatus
  duration_seconds: number | null
  voice: string | null
  provider: string | null
  generated_at: string | null
  error_message: string | null
  marks: AudioMark[]
  url: string | null
}

export interface ArticleListItem {
  id: number
  columnist_id: number
  title: string
  author: string | null
  outlet: string | null
  canonical_url: string
  published_at: string | null
  summary: string | null
  reading_minutes: number
  word_count: number
  is_paywalled: boolean
  is_read: boolean
  is_listened: boolean
  is_archived: boolean
  is_favorite: boolean
  audio_position_seconds: number
  audio_id: number | null
  audio_status: AudioStatus | null
  audio_duration: number | null
}

export interface ArticleDetail extends ArticleListItem {
  body: Block[]
  plain_text: string
  original_url: string | null
  extractor_used: string | null
  reading_paragraph_index: number
  audio: AudioInfo | null
}

export interface InboxGroup {
  columnist_id: number
  columnist_name: string
  outlet: string
  articles: ArticleListItem[]
}

export interface Inbox {
  date: string
  total: number
  unread: number
  groups: InboxGroup[]
  last_run_at: string | null
}

export interface Preferences {
  collect_hour: number
  collect_minute: number
  timezone: string
  tts_provider: string
  tts_voice: string
  auto_generate_audio: boolean
  playback_rate: number
  retention_months: number
  theme: 'light' | 'dark' | 'system'
  font_size: number
}

export interface TtsVoice {
  id: string
  label: string
  language: string
  description: string
}

export interface TtsProvider {
  key: string
  label: string
  configured: boolean
  voices: TtsVoice[]
}

export interface Credential {
  id: number
  outlet: string
  kind: string
  label: string | null
  has_secret: boolean
  cookie_names: string[]
  updated_at: string
  last_used_at: string | null
}

export interface SourceHealthDay {
  date: string
  status: string
  found: number
  new: number
  ms: number
  error: string | null
}

export interface SourceHealth {
  columnist_id: number
  name: string
  outlet: string
  active: boolean
  status: 'sana' | 'degradada' | 'caida' | 'sin-datos'
  consecutive_failures: number
  last_success_at: string | null
  last_error: string | null
  last_days: SourceHealthDay[]
}

export interface SourceRun {
  id: number
  columnist_id: number | null
  columnist_name: string | null
  status: string
  articles_found: number
  articles_new: number
  duration_ms: number
  error_message: string | null
  created_at: string
}

export interface CollectionRun {
  id: number
  started_at: string
  finished_at: string | null
  trigger: string
  status: string
  sources_total: number
  sources_failed: number
  articles_new: number
  source_runs: SourceRun[]
}

export interface Stats {
  articles_total: number
  articles_unread: number
  audios_ready: number
  audios_error: number
  sources_active: number
  last_run: {
    at: string | null
    status: string | null
    new_articles: number
    sources_failed: number
  } | null
}

export interface SearchResult {
  total: number
  page: number
  size: number
  items: ArticleListItem[]
}
