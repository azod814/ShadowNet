from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_file,
    send_from_directory,
    abort
)

import requests
from bs4 import BeautifulSoup
import sqlite3
import uuid
import os
import re
import zipfile
import shutil
from urllib.parse import urljoin, urlparse, urldefrag
from datetime import datetime

from config import Config


app = Flask(__name__)
app.config.from_object(Config)

os.makedirs(app.config["PROJECTS_DIR"], exist_ok=True)
os.makedirs(app.config["ASSETS_DIR"], exist_ok=True)


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


def normalize_url(url):
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


def safe_filename(name, fallback="file"):
    name = name.split("?")[0]
    name = os.path.basename(name)

    name = re.sub(r"[^a-zA-Z0-9_.-]", "_", name)

    if not name:
        name = fallback

    return name


def is_same_domain(source_url, candidate_url):
    source = urlparse(source_url)
    candidate = urlparse(candidate_url)

    return (
        candidate.netloc == source.netloc
        and candidate.scheme in ("http", "https")
    )


def get_page_filename(url, used_names):
    parsed = urlparse(url)

    path = parsed.path.strip("/")

    if not path:
        base = "index"
    else:
        base = re.sub(r"[^a-zA-Z0-9_-]", "_", path.replace("/", "_"))
        base = base[:80]

    filename = f"{base}.html"

    counter = 2

    while filename in used_names:
        filename = f"{base}_{counter}.html"
        counter += 1

    used_names.add(filename)

    return filename


def download_asset(asset_url, asset_dir, asset_map):
    if not asset_url or asset_url.startswith("data:"):
        return asset_url

    if asset_url in asset_map:
        return asset_map[asset_url]

    try:
        response = requests.get(
            asset_url,
            timeout=app.config["REQUEST_TIMEOUT"],
            headers={
                "User-Agent": "ShadowNet-Website-Replica-Studio/2.0"
            }
        )

        if response.status_code != 200:
            return asset_url

        content_type = response.headers.get("Content-Type", "")
        parsed = urlparse(asset_url)

        extension = os.path.splitext(parsed.path)[1]

        if not extension:
            if "image" in content_type:
                extension = ".img"
            elif "javascript" in content_type:
                extension = ".js"
            elif "css" in content_type:
                extension = ".css"
            else:
                extension = ".asset"

        filename = safe_filename(
            os.path.basename(parsed.path),
            fallback=f"asset_{uuid.uuid4().hex[:10]}{extension}"
        )

        if not filename.endswith(extension) and extension:
            filename += extension

        destination = os.path.join(asset_dir, filename)

        counter = 2
        base, ext = os.path.splitext(filename)

        while os.path.exists(destination):
            filename = f"{base}_{counter}{ext}"
            destination = os.path.join(asset_dir, filename)
            counter += 1

        with open(destination, "wb") as file:
            file.write(response.content)

        local_path = f"assets/{filename}"
        asset_map[asset_url] = local_path

        return local_path

    except Exception:
        return asset_url


def rewrite_assets(soup, page_url, project_dir, asset_map):
    asset_dir = os.path.join(project_dir, "assets")
    os.makedirs(asset_dir, exist_ok=True)

    asset_count = 0
    max_assets = app.config["MAX_ASSETS_PER_PAGE"]

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
                ):
                    continue

            absolute_url = urljoin(page_url, value)

            parsed = urlparse(absolute_url)

            if parsed.scheme not in ("http", "https"):
                continue

            local_path = download_asset(
                absolute_url,
                asset_dir,
                asset_map
            )

            if local_path != absolute_url:
                tag[attribute] = local_path
                asset_count += 1

    return asset_count


def create_project(source_url):
    project_id = uuid.uuid4().hex[:12]

    project_dir = os.path.join(
        app.config["PROJECTS_DIR"],
        project_id
    )

    os.makedirs(project_dir, exist_ok=True)
    os.makedirs(
        os.path.join(project_dir, "assets"),
        exist_ok=True
    )

    return project_id, project_dir


def fetch_page(url):
    response = requests.get(
        url,
        timeout=app.config["REQUEST_TIMEOUT"],
        headers={
            "User-Agent": "Mozilla/5.0 ShadowNet Replica Studio"
        }
    )

    response.raise_for_status()

    return response


@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/analyze", methods=["POST"])
def analyze_website():
    data = request.get_json(silent=True) or {}

    source_url = normalize_url(data.get("url", ""))

    if not source_url:
        return jsonify({
            "success": False,
            "error": "Please enter a valid HTTP or HTTPS URL."
        }), 400

    try:
        project_id, project_dir = create_project(source_url)

        response = fetch_page(source_url)
        soup = BeautifulSoup(response.text, "lxml")

        page_title = (
            soup.title.get_text(strip=True)
            if soup.title else "Untitled Website"
        )

        discovered_urls = [source_url]
        seen_urls = {urldefrag(source_url)[0]}

        for link in soup.find_all("a", href=True):
            absolute_url = urldefrag(
                urljoin(source_url, link["href"])
            )[0]

            if (
                absolute_url
                and is_same_domain(source_url, absolute_url)
                and absolute_url not in seen_urls
            ):
                seen_urls.add(absolute_url)
                discovered_urls.append(absolute_url)

            if (
                len(discovered_urls)
                >= app.config["MAX_PAGES_PER_PROJECT"]
            ):
                break

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO projects
            (id, source_url, title, status, created_at, pages_count, assets_count)
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

        asset_map = {}
        used_names = set()

        pages_created = []
        total_assets = 0

        for page_url in discovered_urls:
            try:
                page_response = fetch_page(page_url)

                page_soup = BeautifulSoup(
                    page_response.text,
                    "lxml"
                )

                filename = get_page_filename(
                    page_url,
                    used_names
                )

                assets = rewrite_assets(
                    page_soup,
                    page_url,
                    project_dir,
                    asset_map
                )

                total_assets += assets

                local_path = os.path.join(
                    project_dir,
                    filename
                )

                with open(
                    local_path,
                    "w",
                    encoding="utf-8"
                ) as file:
                    file.write(str(page_soup))

                page_id = uuid.uuid4().hex[:12]

                current_title = (
                    page_soup.title.get_text(strip=True)
                    if page_soup.title
                    else filename
                )

                cursor.execute("""
                    INSERT INTO pages
                    (id, project_id, original_url, local_file, title, created_at)
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
                    "title": current_title
                })

            except Exception:
                continue

        cursor.execute("""
            UPDATE projects
            SET status=?, pages_count=?, assets_count=?
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
            shutil.rmtree(project_dir, ignore_errors=True)

            return jsonify({
                "success": False,
                "error": "The website could not be analyzed."
            }), 500

        return jsonify({
            "success": True,
            "project_id": project_id,
            "title": page_title,
            "source_url": source_url,
            "pages_count": len(pages_created),
            "assets_count": total_assets,
            "pages": pages_created,
            "preview_url": f"/preview/{project_id}"
        })

    except requests.exceptions.RequestException as error:
        return jsonify({
            "success": False,
            "error": f"Could not connect to the website: {str(error)}"
        }), 500

    except Exception as error:
        return jsonify({
            "success": False,
            "error": f"Analysis failed: {str(error)}"
        }), 500


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
        "projects": [dict(project) for project in projects]
    })


@app.route("/api/project/<project_id>")
def get_project(project_id):
    conn = get_db()

    project = conn.execute("""
        SELECT *
        FROM projects
        WHERE id=?
    """, (project_id,)).fetchone()

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
    """, (project_id,)).fetchall()

    conn.close()

    return jsonify({
        "success": True,
        "project": dict(project),
        "pages": [dict(page) for page in pages]
    })


@app.route("/preview/<project_id>")
def project_preview(project_id):
    conn = get_db()

    page = conn.execute("""
        SELECT *
        FROM pages
        WHERE project_id=?
        ORDER BY created_at ASC
        LIMIT 1
    """, (project_id,)).fetchone()

    conn.close()

    if not page:
        abort(404)

    return render_template(
        "preview.html",
        project_id=project_id,
        page=page
    )


@app.route("/preview/<project_id>/page/<page_id>")
def preview_page(project_id, page_id):
    conn = get_db()

    page = conn.execute("""
        SELECT *
        FROM pages
        WHERE id=? AND project_id=?
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

    if not os.path.exists(file_path):
        abort(404)

    with open(
        file_path,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as file:
        return file.read()


@app.route("/generated/<project_id>/<path:filename>")
def serve_generated_file(project_id, filename):
    project_dir = os.path.join(
        app.config["PROJECTS_DIR"],
        project_id
    )

    return send_from_directory(
        project_dir,
        filename
    )


@app.route("/api/project/<project_id>/export")
def export_project(project_id):
    project_dir = os.path.join(
        app.config["PROJECTS_DIR"],
        project_id
    )

    if not os.path.exists(project_dir):
        return jsonify({
            "success": False,
            "error": "Project not found."
        }), 404

    export_dir = os.path.join(
        app.config["PROJECTS_DIR"],
        "_exports"
    )

    os.makedirs(export_dir, exist_ok=True)

    zip_path = os.path.join(
        export_dir,
        f"ShadowNet_{project_id}.zip"
    )

    with zipfile.ZipFile(
        zip_path,
        "w",
        zipfile.ZIP_DEFLATED
    ) as archive:

        for root, _, files in os.walk(project_dir):
            for file in files:
                full_path = os.path.join(root, file)

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
        download_name=f"ShadowNet_{project_id}.zip"
    )


@app.route("/api/project/<project_id>", methods=["DELETE"])
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

    conn.execute(
        "DELETE FROM pages WHERE project_id=?",
        (project_id,)
    )

    conn.execute(
        "DELETE FROM projects WHERE id=?",
        (project_id,)
    )

    conn.commit()
    conn.close()

    return jsonify({
        "success": True
    })


if __name__ == "__main__":
    init_db()

    app.run(
        debug=True,
        host=app.config["HOST"],
        port=app.config["PORT"]
    )
