import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
env = root / ".env"
if not env.exists():
    env.write_text(
        (root / ".env.example").read_text(encoding="utf-8"), encoding="utf-8"
    )
text = env.read_text(encoding="utf-8")
text = text.replace(
    "JWT_SECRET=CHANGE_ME_TO_A_RANDOM_SECRET_AT_LEAST_32_CHARACTERS",
    "JWT_SECRET=" + secrets.token_urlsafe(48),
)
text = text.replace(
    "BOOTSTRAP_ADMIN_PASSWORD=CHANGE_ME_AT_LEAST_12_CHARACTERS",
    "BOOTSTRAP_ADMIN_PASSWORD=" + secrets.token_urlsafe(18),
)
env.write_text(text, encoding="utf-8")
print(
    "Local signing secret and initial admin password are in .env (not printed, not tracked by Git)."
)
