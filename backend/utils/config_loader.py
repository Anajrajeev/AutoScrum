"""Configuration management for AutoScrum."""

import os
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from pydantic import Field

# Load environment variables
load_dotenv()


class OpenAIConfig(BaseSettings):
    """OpenAI configuration."""
    api_key: str = Field(..., alias="OPENAI_API_KEY")
    model: str = Field(default="gpt-4", alias="OPENAI_MODEL")


class DatabaseConfig(BaseSettings):
    """Database configuration."""
    url: str = Field(
        default="postgresql://autoscrum_user:autoscrum_pass@localhost:5432/autoscrum_db",
        alias="DATABASE_URL"
    )


class RedisConfig(BaseSettings):
    """Redis configuration."""
    host: str = Field(default="localhost", alias="REDIS_HOST")
    port: int = Field(default=6379, alias="REDIS_PORT")
    db: int = Field(default=0, alias="REDIS_DB")
    password: Optional[str] = Field(default=None, alias="REDIS_PASSWORD")


class JiraConfig(BaseSettings):
    """Jira configuration."""
    base_url: str = Field(..., alias="JIRA_BASE_URL")
    email: str = Field(..., alias="JIRA_EMAIL")
    api_token: str = Field(..., alias="JIRA_API_TOKEN")


class ServiceNowConfig(BaseSettings):
    """ServiceNow configuration."""
    instance: str = Field(..., alias="SERVICENOW_INSTANCE")
    username: str = Field(..., alias="SERVICENOW_USERNAME")
    password: str = Field(..., alias="SERVICENOW_PASSWORD")


class ApplicationConfig(BaseSettings):
    """Application configuration."""
    env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")


class CeleryConfig(BaseSettings):
    """Celery configuration."""
    broker_url: str = Field(
        default="redis://localhost:6379/1",
        alias="CELERY_BROKER_URL"
    )
    result_backend: str = Field(
        default="redis://localhost:6379/1",
        alias="CELERY_RESULT_BACKEND"
    )


class AppConfig:
    """Main application configuration container."""
    
    def __init__(self):
        """Initialize all configurations."""
        self.openai = self._safe_load(OpenAIConfig)
        self.database = self._safe_load(DatabaseConfig)
        self.redis = self._safe_load(RedisConfig)
        self.jira = self._safe_load(JiraConfig)
        self.servicenow = self._safe_load(ServiceNowConfig)
        self.app = self._safe_load(ApplicationConfig)
        self.celery = self._safe_load(CeleryConfig)
    
    @staticmethod
    def _safe_load(config_class):
        """
        Safely load configuration, return None if required fields missing.
        
        Args:
            config_class: Pydantic settings class to load
            
        Returns:
            Config instance or None
        """
        try:
            return config_class()
        except Exception as e:
            # Return None for optional configs (MCP integrations)
            if config_class in [JiraConfig, ServiceNowConfig]:
                return None
            # Re-raise for required configs
            raise e
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary (excluding sensitive data).
        
        Returns:
            Dictionary with configuration
        """
        return {
            "app": {
                "env": self.app.env if self.app else None,
                "log_level": self.app.log_level if self.app else None,
            },
            "openai_configured": self.openai is not None,
            "database_configured": self.database is not None,
            "redis_configured": self.redis is not None,
            "jira_configured": self.jira is not None,
            "servicenow_configured": self.servicenow is not None,
        }


# Singleton config instance
_config: Optional[AppConfig] = None


def load_config() -> AppConfig:
    """
    Load application configuration.
    
    Returns:
        AppConfig instance
    """
    return AppConfig()


def get_config() -> AppConfig:
    """
    Get or create configuration singleton.
    
    Returns:
        AppConfig instance
    """
    global _config
    if _config is None:
        _config = load_config()
    return _config

