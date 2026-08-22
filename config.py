import os


BASE_DIR = os.path.abspath(
    os.path.dirname(__file__)
)


class Config:
    # Flask security key
    SECRET_KEY = (
        os.environ.get("SECRET_KEY")
        or "shadownet-local-development-key-change-in-production"
    )

    # Project database
    DATABASE = os.path.join(
        BASE_DIR,
        "shadownet.db"
    )

    # Server
    HOST = "127.0.0.1"
    PORT = 5000

    # Generated project directories
    PROJECTS_DIR = os.path.join(
        BASE_DIR,
        "generated_projects"
    )

    ASSETS_DIR = os.path.join(
        BASE_DIR,
        "static",
        "generated_assets"
    )

    # Website analysis limits
    REQUEST_TIMEOUT = 15
    MAX_PAGES_PER_PROJECT = 10
    MAX_ASSETS_PER_PAGE = 100

    # Allowed protocols
    ALLOWED_SCHEMES = {
        "http",
        "https"
    }

    # Maximum exported project size
    MAX_PROJECT_SIZE_MB = 100
