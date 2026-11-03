from dataclasses import dataclass
from pathlib import Path
import os, secrets

@dataclass
class Settings:
    environment: str = os.getenv('APP_ENV', 'development')
    database_url: str = os.getenv('DATABASE_URL', 'sqlite:///./var/app.db')
    storage_dir: Path = Path(os.getenv('STORAGE_DIR', './var/storage'))
    public_url: str = os.getenv('PUBLIC_URL', 'http://127.0.0.1:8000')
    secret: str = os.getenv('SIGNING_SECRET', '')
    appid: str = os.getenv('WECHAT_APPID', '')
    appsecret: str = os.getenv('WECHAT_APPSECRET', '')
    dev_login: bool = os.getenv('ALLOW_DEV_LOGIN', '0') == '1'
    pose_model: str = os.getenv('POSE_MODEL', '')
    pose_python: str = os.getenv('POSE_PYTHON', '')
    max_bytes: int = int(os.getenv('MAX_VIDEO_BYTES', str(300 * 1024 * 1024)))
    max_seconds: int = int(os.getenv('MAX_VIDEO_SECONDS', '180'))
    def prepare(self):
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        if self.environment == 'production':
            if self.dev_login or len(self.secret) < 32 or not self.appid or not self.appsecret:
                raise RuntimeError('Production requires WeChat credentials, >=32-char signing secret, and disabled dev login')
            if not self.public_url.startswith('https://'):
                raise RuntimeError('Production PUBLIC_URL must use HTTPS')
        if not self.secret:
            key = self.storage_dir.parent / '.signing-key'
            if not key.exists():
                try:
                    with key.open('x') as f: f.write(secrets.token_urlsafe(48))
                    key.chmod(0o600)
                except FileExistsError: pass
            self.secret = key.read_text().strip()
        if self.database_url.startswith('sqlite:///'):
            Path(self.database_url.removeprefix('sqlite:///')).parent.mkdir(parents=True, exist_ok=True)
