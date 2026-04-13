from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from urllib.parse import quote_plus


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore', case_sensitive=True)

    app_name: str = 'Scheduler API'
    database_url: str | None = Field(default=None, validation_alias=AliasChoices('DATABASE_URL', 'database_url'))
    user: str | None = Field(default=None, validation_alias='user')
    password: str | None = Field(default=None, validation_alias='password')
    host: str | None = Field(default=None, validation_alias='host')
    port: int | None = Field(default=None, validation_alias='port')
    dbname: str | None = Field(default=None, validation_alias='dbname')
    jwt_secret: str = Field(default='change-me', validation_alias=AliasChoices('JWT_SECRET', 'jwt_secret'))
    jwt_algorithm: str = Field(default='HS256', validation_alias=AliasChoices('JWT_ALGORITHM', 'jwt_algorithm'))
    access_token_minutes: int = Field(default=120, validation_alias=AliasChoices('ACCESS_TOKEN_MINUTES', 'access_token_minutes'))

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        user = quote_plus(self.user or 'postgres')
        password = quote_plus(self.password or 'postgres')
        host = self.host or 'localhost'
        port = self.port or 5432
        dbname = self.dbname or 'postgres'
        return f'postgresql+asyncpg://{user}:{password}@{host}:{port}/{dbname}?ssl=require'


settings = Settings()
