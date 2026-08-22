from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_file,
    send_from_directory,
    abort,
    Response
)

import requests
from bs4 import BeautifulSoup
import sqlite3
import uuid
import os
import re
import zipfile
import shutil

from urllib.parse import (
    urljoin,
    urlparse,
    urldefrag
)

from datetime import datetime


# =========================================================
# APP SETUP
# =========================================================

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)

app.config.update(
    SECRET_KEY="shadownet_replica_studio_local",
    DATABASE=os.path.join(BASE_DIR, "shadownet.db"),
    PROJECTS_DIR=os.path.join(BASE_DIR, "generated_projects"),
    ASSETS_DIR=os.path.join(BASE_DIR, "generated_projects", "_assets"),
    HOST="127.0.0.1",
    PORT=5000,
    REQUEST_TIMEOUT=10,
    MAX_PAGES_PER_PROJECT=3,
    MAX_ASSETS_PER_PAGE=30,
    ALLOWED_SCHEMES=("http", "https")
)

os.makedirs(app.config["PROJECTS_DIR"], exist_ok=True)
os.makedirs(app.config["ASSETS_DIR"], exist_ok=True)


# =========================================================
# DATABASE
# =========================================================

def get_db():
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            source_url TEXT NOT NULL,
            title TEXT,
            status TEXT,
            created_at TEXT,
            pages_count INTEGER DEFAULT 0,
            assets_count INTEGER DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pages (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            original_url TEXT,
            local_file TEXT,
            title TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


# =========================================================
# URL HELPERS
# =========================================================

def normalize_url(url):
    if not url:
        return None

    url = url.strip()

    if not url:
        return None

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urlparse(url)

    if parsed.scheme not in app.config["ALLOWED_SCHEMES"]:
        return None

    if not parsed.netloc:
        return None

    return url


def clean_url(url):
    if not url:
        return ""

    return urldefrag(url)[0].rstrip("/")


def is_same_domain(source_url, candidate_url):
    source = urlparse(source_url)
    candidate = urlparse(candidate_url)

    return (
        candidate.netloc == source.netloc
        and candidate.scheme in ("http", "https")
    )


def safe_filename(name, fallback="file"):
    name = name.split("?")[0]
    name = os.path.basename(name)

    name = re.sub(
        r"[^a-zA-Z0-9_.-]",
        "_",
        name
    )

    if not name:
        name = fallback

    return name


def get_page_filename(url, used_names):
    parsed = urlparse(url)

    path = parsed.path.strip("/")

    if not path:
        base = "index"
    else:
        base = re.sub(
            r"[^a-zA-Z0-9_-]",
            "_",
            path.replace("/", "_")
        )

        base = base[:80]

    if not base:
        base = "page"

    filename = f"{base}.html"

    counter = 2

    while filename in used_names:
        filename = f"{base}_{counter}.html"
        counter += 1

    used_names.add(filename)

    return filename


# =========================================================
# PROJECT HELPERS
# =========================================================

def create_project(source_url):
    project_id = uuid.uuid4().hex[:12]

    project_dir = os.path.join(
        app.config["PROJECTS_DIR"],
        project_id
    )

    assets_dir = os.path.join(
        project_dir,
        "assets"
    )

    os.makedirs(project_dir, exist_ok=True)
    os.makedirs(assets_dir, exist_ok=True)

    return project_id, project_dir


def fetch_page(url):
    response = requests.get(
        url,
        timeout=app.config["REQUEST_TIMEOUT"],
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/120 Safari/537.36"
            )
        }
    )

    response.raise_for_status()

    return response


# =========================================================
# ASSET DOWNLOAD
# =========================================================

def download_asset(
    asset_url,
    asset_dir,
    asset_map,
    project_id
):
    if not asset_url:
        return asset_url

    if asset_url.startswith("data:"):
        return asset_url

    if asset_url in asset_map:
        return asset_map[asset_url]

    try:
        response = requests.get(
            asset_url,
            timeout=app.config["REQUEST_TIMEOUT"],
            headers={
                "User-Agent": "ShadowNet Replica Studio/2.0"
            }
        )

        if response.status_code != 200:
            return asset_url

        content_type = response.headers.get(
            "Content-Type",
            ""
        )

        parsed = urlparse(asset_url)

        extension = os.path.splitext(
            parsed.path
        )[1]

        if not extension:
            if "image" in content_type:
                extension = ".img"
            elif "javascript" in content_type:
                extension = ".js"
            elif "css" in content_type:
                extension = ".css"
            elif "font" in content_type:
                extension = ".font"
            else:
                extension = ".asset"

        filename = safe_filename(
            os.path.basename(parsed.path),
            fallback=(
                f"asset_{uuid.uuid4().hex[:10]}"
                f"{extension}"
            )
        )

        if extension and not filename.endswith(extension):
            filename += extension

        destination = os.path.join(
            asset_dir,
            filename
        )

        counter = 2
        base, ext = os.path.splitext(filename)

        while os.path.exists(destination):
            filename = f"{base}_{counter}{ext}"
            destination = os.path.join(
                asset_dir,
                filename
            )
            counter += 1

        with open(destination, "wb") as file:
            file.write(response.content)

        local_url = (
            f"/generated/{project_id}/assets/{filename}"
        )

        asset_map[asset_url] = local_url

        return local_url

    except Exception as error:
        print(
            f"[ASSET ERROR] {asset_url}: {error}"
        )

        return asset_url


def rewrite_assets(
    soup,
    page_url,
    project_dir,
    asset_map,
    project_id
):
    asset_dir = os.path.join(
        project_dir,
        "assets"
    )

    os.makedirs(
        asset_dir,
        exist_ok=True
    )

    asset_count = 0

    max_assets = app.config[
        "MAX_ASSETS_PER_PAGE"
    ]

    asset_targets = [
        ("img", "src"),
        ("script", "src"),
        ("link", "href"),
        ("source", "src"),
        ("video", "poster"),
        ("audio", "src"),
    ]

    for tag_name, attribute in asset_targets:

        for tag in soup.find_all(tag_name):

            if asset_count >= max_assets:
                break

            value = tag.get(attribute)

            if not value:
                continue

            if tag_name == "link":
                rel = tag.get("rel", [])

                if (
                    "stylesheet" not in rel
                    and "icon" not in rel
                    and "shortcut" not in rel
                ):
                    continue

            absolute_url = urljoin(
                page_url,
                value
            )

            parsed = urlparse(absolute_url)

            if parsed.scheme not in (
                "http",
                "https"
            ):
                continue

            local_path = download_asset(
                absolute_url,
                asset_dir,
                asset_map,
                project_id
            )

            if local_path != absolute_url:
                tag[attribute] = local_path
                asset_count += 1

    return asset_count


# =========================================================
# INTERNAL PAGE LINKS
# =========================================================

def rewrite_page_links(
    soup,
    current_page_url,
    source_url,
    page_url_map,
    project_id
):
    for link in soup.find_all("a", href=True):

        href = link.get("href", "")

        if not href:
            continue

        if href.startswith((
            "#",
            "javascript:",
            "mailto:",
            "tel:"
        )):
            continue

        absolute_url = clean_url(
            urljoin(
                current_page_url,
                href
            )
        )

        if not absolute_url:
            continue

        if not is_same_domain(
            source_url,
            absolute_url
        ):
            continue

        page_id = page_url_map.get(
            absolute_url
        )

        if page_id:
            link["href"] = (
                f"/preview/{project_id}/page/"
                f"{page_id}"
            )


# =========================================================
# HOME
# =========================================================

@app.route("/")
def dashboard():

    page = {
        "title": "ShadowNet Dashboard",
        "description": (
            "Website Clone & Replica Studio "
            "for authorized development and testing"
        )
    }

    return render_template(
        "dashboard.html",
        page=page
    )


# =========================================================
# ANALYZE WEBSITE
# =========================================================

@app.route(
    "/api/analyze",
    methods=["POST"]
)
def analyze_website():

    data = request.get_json(
        silent=True
    ) or {}

    source_url = normalize_url(
        data.get("url", "")
    )

    if not source_url:
        return jsonify({
            "success": False,
            "error": (
                "Please enter a valid HTTP "
                "or HTTPS URL."
            )
        }), 400

    try:

        print(
            f"[INFO] Starting analysis: "
            f"{source_url}"
        )

        project_id, project_dir = create_project(
            source_url
        )

        response = fetch_page(source_url)

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        page_title = (
            soup.title.get_text(strip=True)
            if soup.title
            else "Untitled Website"
        )

        discovered_urls = [source_url]

        seen_urls = {
            clean_url(source_url)
        }

        for link in soup.find_all(
            "a",
            href=True
        ):

            absolute_url = clean_url(
                urljoin(
                    source_url,
                    link["href"]
                )
            )

            if (
                absolute_url
                and is_same_domain(
                    source_url,
                    absolute_url
                )
                and absolute_url not in seen_urls
            ):

                seen_urls.add(
                    absolute_url
                )

                discovered_urls.append(
                    absolute_url
                )

            if (
                len(discovered_urls)
                >= app.config[
                    "MAX_PAGES_PER_PROJECT"
                ]
            ):
                break

        print(
            f"[INFO] Pages discovered: "
            f"{len(discovered_urls)}"
        )

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO projects
            (
                id,
                source_url,
                title,
                status,
                created_at,
                pages_count,
                assets_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            project_id,
            source_url,
            page_title,
            "analyzing",
            datetime.now().isoformat(),
            0,
            0
        ))

        conn.commit()

        used_names = set()
        page_records = []

        for page_url in discovered_urls:

            page_id = uuid.uuid4().hex[:12]

            filename = get_page_filename(
                page_url,
                used_names
            )

            page_records.append({
                "id": page_id,
                "url": page_url,
                "file": filename
            })

        page_url_map = {}

        for record in page_records:
            page_url_map[
                clean_url(record["url"])
            ] = record["id"]

        asset_map = {}
        pages_created = []
        total_assets = 0

        for record in page_records:

            page_id = record["id"]
            page_url = record["url"]
            filename = record["file"]

            try:

                print(
                    f"[INFO] Processing: "
                    f"{page_url}"
                )

                page_response = fetch_page(
                    page_url
                )

                page_soup = BeautifulSoup(
                    page_response.text,
                    "html.parser"
                )

                assets = rewrite_assets(
                    page_soup,
                    page_url,
                    project_dir,
                    asset_map,
                    project_id
                )

                total_assets += assets

                rewrite_page_links(
                    page_soup,
                    page_url,
                    source_url,
                    page_url_map,
                    project_id
                )

                local_path = os.path.join(
                    project_dir,
                    filename
                )

                with open(
                    local_path,
                    "w",
                    encoding="utf-8",
                    errors="ignore"
                ) as file:

                    file.write(
                        str(page_soup)
                    )

                current_title = (
                    page_soup.title.get_text(
                        strip=True
                    )
                    if page_soup.title
                    else filename
                )

                cursor.execute("""
                    INSERT INTO pages
                    (
                        id,
                        project_id,
                        original_url,
                        local_file,
                        title,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    page_id,
                    project_id,
                    page_url,
                    filename,
                    current_title,
                    datetime.now().isoformat()
                ))

                pages_created.append({
                    "id": page_id,
                    "url": page_url,
                    "file": filename,
                    "title": current_title,
                    "preview_url": (
                        f"/preview/{project_id}/page/"
                        f"{page_id}"
                    )
                })

            except Exception as error:

                print(
                    f"[PAGE ERROR] "
                    f"{page_url}: {error}"
                )

                continue

        cursor.execute("""
            UPDATE projects
            SET
                status=?,
                pages_count=?,
                assets_count=?
            WHERE id=?
        """, (
            "ready",
            len(pages_created),
            total_assets,
            project_id
        ))

        conn.commit()
        conn.close()

        if not pages_created:

            shutil.rmtree(
                project_dir,
                ignore_errors=True
            )

            return jsonify({
                "success": False,
                "error": (
                    "The website could not "
                    "be analyzed."
                )
            }), 500

        print(
            f"[SUCCESS] Project created: "
            f"{project_id}"
        )

        return jsonify({
            "success": True,
            "project_id": project_id,
            "title": page_title,
            "source_url": source_url,
            "pages_count": len(
                pages_created
            ),
            "assets_count": total_assets,
            "pages": pages_created,
            "preview_url": (
                f"/preview/{project_id}"
            ),
            "first_page_preview": (
                pages_created[0][
                    "preview_url"
                ]
            )
        })

    except requests.exceptions.RequestException as error:

        return jsonify({
            "success": False,
            "error": (
                "Could not connect to the "
                f"website: {str(error)}"
            )
        }), 500

    except Exception as error:

        print(
            f"[CRITICAL ERROR] {error}"
        )

        return jsonify({
            "success": False,
            "error": (
                f"Analysis failed: {str(error)}"
            )
        }), 500


# =========================================================
# GET ALL PROJECTS
# =========================================================

@app.route("/api/projects")
def get_projects():

    conn = get_db()

    projects = conn.execute("""
        SELECT *
        FROM projects
        ORDER BY created_at DESC
    """).fetchall()

    conn.close()

    return jsonify({
        "success": True,
        "projects": [
            dict(project)
            for project in projects
        ]
    })


# =========================================================
# GET SINGLE PROJECT
# =========================================================

@app.route(
    "/api/project/<project_id>"
)
def get_project(project_id):

    conn = get_db()

    project = conn.execute("""
        SELECT *
        FROM projects
        WHERE id=?
    """, (
        project_id,
    )).fetchone()

    if not project:

        conn.close()

        return jsonify({
            "success": False,
            "error": "Project not found."
        }), 404

    pages = conn.execute("""
        SELECT *
        FROM pages
        WHERE project_id=?
        ORDER BY created_at ASC
    """, (
        project_id,
    )).fetchall()

    conn.close()

    pages_list = []

    for page in pages:

        page_data = dict(page)

        page_data["preview_url"] = (
            f"/preview/{project_id}/page/"
            f"{page['id']}"
        )

        pages_list.append(
            page_data
        )

    return jsonify({
        "success": True,
        "project": dict(project),
        "pages": pages_list
    })


# =========================================================
# PROJECT PREVIEW
# =========================================================

@app.route(
    "/preview/<project_id>"
)
def project_preview(project_id):

    conn = get_db()

    page = conn.execute("""
        SELECT *
        FROM pages
        WHERE project_id=?
        ORDER BY created_at ASC
        LIMIT 1
    """, (
        project_id,
    )).fetchone()

    conn.close()

    if not page:
        abort(404)

    return render_template(
        "preview.html",
        project_id=project_id,
        page=dict(page),
        page_id=page["id"],
        page_preview_url=(
            f"/preview/{project_id}/page/"
            f"{page['id']}"
        )
    )


# =========================================================
# DIRECT PAGE PREVIEW
# =========================================================

@app.route(
    "/preview/<project_id>/page/<page_id>"
)
def preview_page(
    project_id,
    page_id
):

    if not project_id or not page_id:
        abort(404)

    conn = get_db()

    page = conn.execute("""
        SELECT *
        FROM pages
        WHERE
            id=?
            AND project_id=?
    """, (
        page_id,
        project_id
    )).fetchone()

    conn.close()

    if not page:
        abort(404)

    file_path = os.path.join(
        app.config["PROJECTS_DIR"],
        project_id,
        page["local_file"]
    )

    if not os.path.isfile(
        file_path
    ):
        abort(404)

    try:

        with open(
            file_path,
            "r",
            encoding="utf-8",
            errors="ignore"
        ) as file:

            content = file.read()

        return Response(
            content,
            status=200,
            mimetype="text/html"
        )

    except Exception as error:

        print(
            f"[PREVIEW ERROR] {error}"
        )

        abort(500)


# =========================================================
# SERVE GENERATED FILES
# =========================================================

@app.route(
    "/generated/<project_id>/<path:filename>"
)
def serve_generated_file(
    project_id,
    filename
):

    project_dir = os.path.join(
        app.config["PROJECTS_DIR"],
        project_id
    )

    if not os.path.isdir(
        project_dir
    ):
        abort(404)

    return send_from_directory(
        project_dir,
        filename
    )


# =========================================================
# EXPORT PROJECT
# =========================================================

@app.route(
    "/api/project/<project_id>/export"
)
def export_project(project_id):

    project_dir = os.path.join(
        app.config["PROJECTS_DIR"],
        project_id
    )

    if not os.path.exists(
        project_dir
    ):
        return jsonify({
            "success": False,
            "error": "Project not found."
        }), 404

    export_dir = os.path.join(
        app.config["PROJECTS_DIR"],
        "_exports"
    )

    os.makedirs(
        export_dir,
        exist_ok=True
    )

    zip_path = os.path.join(
        export_dir,
        f"ShadowNet_{project_id}.zip"
    )

    with zipfile.ZipFile(
        zip_path,
        "w",
        zipfile.ZIP_DEFLATED
    ) as archive:

        for root, _, files in os.walk(
            project_dir
        ):

            for file in files:

                full_path = os.path.join(
                    root,
                    file
                )

                archive_name = os.path.relpath(
                    full_path,
                    project_dir
                )

                archive.write(
                    full_path,
                    archive_name
                )

    return send_file(
        zip_path,
        as_attachment=True,
        download_name=(
            f"ShadowNet_{project_id}.zip"
        )
    )


# =========================================================
# DELETE PROJECT
# =========================================================

@app.route(
    "/api/project/<project_id>",
    methods=["DELETE"]
)
def delete_project(project_id):

    project_dir = os.path.join(
        app.config["PROJECTS_DIR"],
        project_id
    )

    shutil.rmtree(
        project_dir,
        ignore_errors=True
    )

    conn = get_db()

    conn.execute("""
        DELETE FROM pages
        WHERE project_id=?
    """, (
        project_id,
    ))

    conn.execute("""
        DELETE FROM projects
        WHERE id=?
    """, (
        project_id,
    ))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": "Project deleted successfully."
    })


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    init_db()

    print("=" * 55)
    print("ShadowNet Replica Studio Started")
    print(
        f"Local URL: "
        f"http://{app.config['HOST']}:"
        f"{app.config['PORT']}"
    )
    print("=" * 55)

    app.run(
        debug=True,
        host=app.config["HOST"],
        port=app.config["PORT"],
        use_reloader=False
    )
