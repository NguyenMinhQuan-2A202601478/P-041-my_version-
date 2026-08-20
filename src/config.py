import os


class Settings:
    """Cau hinh toan cuc cua ung dung, doc tu bien moi truong (.env).

    Tai sao doc tu bien moi truong (os.getenv) thay vi hardcode gia tri
    trong code? (1) Khong lo secret (API key, JWT secret) len Git khi commit
    code. (2) Co the dung config khac nhau cho dev/staging/production ma
    khong can sua code, chi can doi bien moi truong.
    """

    PROJECT_NAME: str = "CV Assistant"
    API_V1_PREFIX: str = "/api/v1"

    # --- Database ---
    # SQLite (dev): chi la 1 file tren o dia, khong can cai server rieng —
    # phu hop de lap trinh/thu nghiem tren may ca nhan.
    # PostgreSQL (prod): vi du "postgresql://user:pass@host:5432/dbname" —
    # can server rieng nhung on dinh va manh hon khi nhieu nguoi dung cung luc.
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./dev.db")
    # In cau lenh SQL ra console khi True — huu ich luc debug, nhung PHAI tat
    # (False) o production vi co the lo du lieu CV/JD nhay cam ra log.
    DATABASE_ECHO: bool = os.getenv("DATABASE_ECHO", "false").lower() == "true"

    # --- Qdrant (Vector DB dung cho RAG - tim kiem theo Y NGHIA) ---
    QDRANT_URL: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    QDRANT_HOST: str = os.getenv("QDRANT_HOST", "localhost")
    QDRANT_PORT: int = int(os.getenv("QDRANT_PORT", "6333"))

    # --- LLM Service (OpenAI / Claude / Gemini) ---
    # WHY a single provider switch instead of always calling one vendor
    # directly? It lets us swap OpenAI/Claude/Gemini per environment purely
    # via env vars — see ADR-06 in docs/architecture/system_architecture.md.
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")  # openai | anthropic | google
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o")
    # Generic fallback key, kept for simple single-provider local setups.
    # Prefer the per-provider *_API_KEY vars below in multi-provider setups —
    # see get_provider_api_key().
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "3"))
    LLM_TIMEOUT_SECONDS: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))

    # Per-provider API keys. Only the one matching LLM_PROVIDER is required
    # at runtime; the others can stay empty.
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", os.getenv("GEMINI_API_KEY", ""))

    # --- Embeddings (for Qdrant vector search, e.g. semantic skill/JD match) ---
    # WHY a separate embedding model setting? Embedding models are usually
    # smaller/cheaper than chat models (e.g. "text-embedding-3-small" vs
    # "gpt-4o") and Anthropic/Claude does not offer an embeddings endpoint,
    # so this gets its own provider switch independent of LLM_PROVIDER.
    EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "openai")  # openai | google
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

    # --- JWT Auth ---
    # KHONG BAO GIO dung gia tri mac dinh nay trong production. Luon dat
    # JWT_SECRET_KEY qua bien moi truong voi 1 chuoi ngau nhien, dai (>=32 ky
    # tu), bi mat — day la "chia khoa" de ky va xac minh moi access token.
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "dev-only-insecure-secret-change-me")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))  # 24 gio

    # --- Google OAuth ---
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")

    # --- CORS ---
    # Danh sach domain (phan cach boi dau phay) duoc phep goi API nay tu
    # trinh duyet. Mac dinh chi cho phep frontend Next.js chay local.
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://localhost:3000")

    # --- File upload (F-02: Upload & Parse CV) ---
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10"))
    ALLOWED_CV_EXTENSIONS: tuple[str, ...] = (".pdf", ".docx")

    def get_provider_api_key(self, provider: str | None = None) -> str:
        """Return the API key for `provider` (defaults to LLM_PROVIDER).

        Falls back to the generic LLM_API_KEY if a provider-specific key
        was not set — convenient for quick local setups with one key.
        """
        provider = (provider or self.LLM_PROVIDER).strip().lower()
        by_provider = {
            "openai": self.OPENAI_API_KEY,
            "anthropic": self.ANTHROPIC_API_KEY,
            "claude": self.ANTHROPIC_API_KEY,
            "google": self.GOOGLE_API_KEY,
            "gemini": self.GOOGLE_API_KEY,
        }
        return by_provider.get(provider, "") or self.LLM_API_KEY


settings = Settings()
