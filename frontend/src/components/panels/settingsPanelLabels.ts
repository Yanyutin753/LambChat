import type { SettingCategory } from "../../types";

type Translate = (key: string) => string;

export function buildCategoryLabels(
  t: Translate,
): Record<SettingCategory, string> {
  return {
    frontend: t("categories.frontend"),
    agent: t("categories.agent"),
    llm: t("categories.llm"),
    session: t("categories.session"),
    skills: t("categories.skills"),
    mongodb: t("categories.mongodb"),
    redis: t("categories.redis"),
    checkpoint: t("categories.checkpoint"),
    long_term_storage: t("categories.long_term_storage"),
    memory: t("categories.memory"),
    memory_embedding: t("categories.memory_embedding"),
    memory_search: t("categories.memory_search"),
    memory_storage: t("categories.memory_storage"),
    security: t("categories.security"),
    email: t("categories.email"),
    captcha: t("categories.captcha"),
    sandbox: t("categories.sandbox"),
    s3: t("categories.s3"),
    file_upload: t("categories.file_upload"),
    tools: t("categories.tools"),
    audio_transcription: t("categories.audio_transcription"),
    tracing: t("categories.tracing"),
    user: t("categories.user"),
    oauth: t("categories.oauth"),
  };
}

export function buildSubcategoryLabels(t: Translate): Record<string, string> {
  return {
    display: t("subcategories.display"),
    contact: t("subcategories.contact"),
    general: t("subcategories.general"),
    retry: t("subcategories.retry"),
    cache: t("subcategories.cache"),
    title: t("subcategories.title"),
    events: t("subcategories.events"),
    daytona: t("subcategories.daytona"),
    e2b: t("subcategories.e2b"),
    mcp: t("subcategories.mcp"),
    deferred: t("subcategories.deferred"),
    connection: t("subcategories.connection"),
    langsmith: t("subcategories.langsmith"),
    jwt: t("subcategories.jwt"),
    service: t("subcategories.service"),
    turnstile: t("subcategories.turnstile"),
    bucket: t("subcategories.bucket"),
    limits: t("subcategories.limits"),
    storage: t("subcategories.storage"),
    pool: t("subcategories.pool"),
    postgres: t("subcategories.postgres"),
    registration: t("subcategories.registration"),
    google: t("subcategories.google"),
    github: t("subcategories.github"),
    apple: t("subcategories.apple"),
    api: t("subcategories.api"),
    index: t("subcategories.index"),
    rerank: t("subcategories.rerank"),
    llm: t("subcategories.llm"),
    model: t("subcategories.model"),
    policy: t("subcategories.policy"),
  };
}
