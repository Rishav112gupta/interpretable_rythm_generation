export type Role = "admin" | "approver" | "editor" | "viewer";

export type PostStatus =
  | "DRAFT"
  | "AI_GENERATED"
  | "NEEDS_REVIEW"
  | "APPROVED"
  | "SCHEDULED"
  | "PUBLISHING"
  | "PUBLISHED"
  | "REJECTED"
  | "FAILED";

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  last_login_at: string | null;
}

export interface Category {
  id: number;
  key: string;
  name: string;
  description: string;
  ai_guidance: string;
  color: string;
  default_template_id: number | null;
  is_active: boolean;
  sort_order: number;
}

export interface Template {
  id: number;
  key: string;
  name: string;
  description: string;
  width: number;
  height: number;
  layout: Record<string, unknown>;
  is_active: boolean;
}

export interface ReviewFlag {
  type: string;
  label: string;
  text: string;
  message: string;
}

export interface PostEvent {
  id: number;
  event_type: string;
  from_status: string | null;
  to_status: string | null;
  message: string;
  data: Record<string, unknown>;
  actor_id: number | null;
  created_at: string;
}

export interface Post {
  id: number;
  channel: string;
  status: PostStatus;
  category_id: number | null;
  category_key: string | null;
  category_name: string | null;
  category_color: string | null;
  template_id: number | null;
  schedule_id: number | null;
  idea_id: number | null;
  topic: string;
  target_audience: string;
  tone: string;
  objective: string;
  important_info: string;
  cta: string;
  language: string;
  brand_instructions: string;
  reference_material: string;
  image_instructions: string;
  desired_publish_at: string | null;
  headline: string;
  subtitle: string;
  caption: string;
  alternative_caption: string;
  hashtags: string[];
  content_summary: string;
  image_prompt: string;
  raw_image_url: string;
  image_url: string;
  review_flags: ReviewFlag[];
  missing_information: string[];
  flags_acknowledged: boolean;
  rejected_reason: string;
  approved_at: string | null;
  scheduled_at: string | null;
  published_at: string | null;
  instagram_media_id: string | null;
  instagram_permalink: string;
  published_via_mock: boolean;
  publish_attempts: number;
  next_retry_at: string | null;
  last_error: string;
  like_count: number | null;
  comments_count: number | null;
  llm_provider: string;
  llm_model: string;
  image_provider: string;
  image_model: string;
  prompt_version: string;
  generation_ms: number | null;
  image_generation_ms: number | null;
  regeneration_count: number;
  image_regeneration_count: number;
  generated_at: string | null;
  created_by_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface PostDetail extends Post {
  events: PostEvent[];
  warnings: string[];
}

export interface Idea {
  id: number;
  title: string;
  description: string;
  category_key: string;
  suggested_format: string;
  target_audience: string;
  source: string;
  status: string;
  created_at: string;
}

export interface Schedule {
  id: number;
  name: string;
  mode: "rolling" | "monthly";
  interval_days: number;
  start_date: string;
  end_date: string | null;
  post_time: string;
  timezone: string;
  generation_lead_hours: number;
  auto_generate: boolean;
  auto_schedule_on_approval: boolean;
  category_id: number | null;
  category_rotation: string[];
  template_id: number | null;
  topic_pool: string[];
  target_audience: string;
  tone: string;
  objective: string;
  cta: string;
  language: string;
  is_active: boolean;
  next_slots: string[];
}

export interface Competitor {
  id: number;
  name: string;
  instagram_handle: string;
  website: string;
  notes: string;
  observation_count: number;
}

export interface Observation {
  id: number;
  competitor_id: number;
  content_topic: string;
  content_type: string;
  caption_summary: string;
  visual_style: string;
  posting_frequency: string;
  observed_strategy: string;
  cta_used: string;
  engagement_notes: string;
  source_url: string;
  observed_on: string | null;
  notes: string;
}

export interface Insight {
  id: number;
  insights: Record<string, string[] | string>;
  observation_count: number;
  llm_provider: string;
  llm_model: string;
  use_in_generation: boolean;
  created_at: string;
}

export interface Brand {
  company_name: string;
  description: string;
  target_audience: string;
  brand_voice: string;
  tone: string;
  words_to_use: string[];
  words_to_avoid: string[];
  cta_style: string;
  hashtag_strategy: string;
  default_hashtags: string[];
  visual_style: string;
  content_restrictions: string;
  default_language: string;
  primary_color: string;
  secondary_color: string;
  logo_url: string;
  website: string;
  contact_info: string;
  knowledge: { label: string; value: string }[];
}

export interface InstagramStatus {
  connected: boolean;
  status: string;
  is_mock: boolean;
  username: string;
  ig_user_id: string;
  account_type: string;
  login_type: string;
  token_source: string;
  token_expires_at: string | null;
  token_last_refreshed_at: string | null;
  scopes: string[];
  last_success_at: string | null;
  last_error: string;
  last_error_at: string | null;
  oauth_available: boolean;
  publishing_limit: Record<string, unknown> | null;
}

export interface IntegrationLog {
  id: number;
  source: string;
  level: string;
  message: string;
  details: Record<string, unknown>;
  post_id: number | null;
  created_at: string;
}

export interface AppSettings {
  timezone: string;
  publishing_enabled: boolean;
  sheets_auto_sync: boolean;
  providers: Record<string, string>;
  mock: { llm: boolean; image_generation: boolean; instagram: boolean; google_sheets: boolean };
  public_base_url: string;
  app_env: string;
}

export interface Dashboard {
  counts: {
    total: number;
    draft: number;
    pending_approval: number;
    approved: number;
    scheduled: number;
    published: number;
    failed: number;
    rejected: number;
  };
  next_scheduled: Post | null;
  upcoming: Post[];
  planned_needing_review: Post[];
  recent: Post[];
  recent_errors: IntegrationLog[];
  instagram: InstagramStatus;
  publishing_enabled: boolean;
  timezone: string;
}
