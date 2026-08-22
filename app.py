@app.route("/api/analyze", methods=["POST"])
def analyze_website():
    data = request.get_json(silent=True) or {}
    raw_url = data.get("url", "")

    print("\n" + "=" * 60)
    print(f"[ANALYZE] Request received: {raw_url}")
    print("=" * 60)

    source_url = normalize_url(raw_url)

    if not source_url:
        return jsonify({
            "success": False,
            "error": "Please enter a valid website URL."
        }), 400

    project_id = None
    project_dir = None
    conn = None

    try:
        # 1. Create project
        project_id, project_dir = create_project(source_url)
        print(f"[PROJECT] Created: {project_id}")

        # 2. Fetch main page
        print(f"[FETCH] Downloading: {source_url}")

        response = fetch_page(source_url)

        # Final URL after redirects
        source_url = response.url
        print(f"[FETCH] Final URL: {source_url}")

        soup = BeautifulSoup(response.text, "html.parser")

        page_title = (
            soup.title.get_text(strip=True)
            if soup.title
            else "Untitled Website"
        )

        # 3. Save project in database
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
            "processing",
            datetime.now().isoformat(),
            0,
            0
        ))

        conn.commit()

        # 4. Create MAIN PAGE FIRST
        page_id = uuid.uuid4().hex[:12]
        filename = "index.html"

        asset_map = {}

        print("[ASSETS] Processing main page assets...")

        assets_count = rewrite_assets(
            soup,
            source_url,
            project_dir,
            asset_map,
            project_id
        )

        # 5. Discover only limited internal pages
        discovered_urls = []
        seen_urls = {clean_url(source_url)}

        max_pages = app.config.get(
            "MAX_PAGES_PER_PROJECT",
            3
        )

        for link in soup.find_all("a", href=True):

            href = link.get("href", "").strip()

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
                urljoin(source_url, href)
            )

            if (
                absolute_url
                and is_same_domain(source_url, absolute_url)
                and absolute_url not in seen_urls
            ):
                seen_urls.add(absolute_url)
                discovered_urls.append(absolute_url)

            if len(discovered_urls) >= max_pages - 1:
                break

        # 6. Main page links
        main_page_url_map = {}

        # Generate IDs for discovered pages now
        used_names = {"index.html"}
        discovered_records = []

        for internal_url in discovered_urls:

            internal_page_id = uuid.uuid4().hex[:12]

            internal_filename = get_page_filename(
                internal_url,
                used_names
            )

            discovered_records.append({
                "id": internal_page_id,
                "url": internal_url,
                "file": internal_filename
            })

            main_page_url_map[
                clean_url(internal_url)
            ] = internal_page_id

        # Rewrite links in main page
        rewrite_page_links(
            soup,
            source_url,
            source_url,
            main_page_url_map,
            project_id
        )

        # 7. Save main page
        main_path = os.path.join(
            project_dir,
            filename
        )

        with open(
            main_path,
            "w",
            encoding="utf-8",
            errors="ignore"
        ) as file:
            file.write(str(soup))

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
            source_url,
            filename,
            page_title,
            datetime.now().isoformat()
        ))

        pages_created = [{
            "id": page_id,
            "url": source_url,
            "file": filename,
            "title": page_title,
            "preview_url": (
                f"/preview/{project_id}/page/{page_id}"
            )
        }]

        conn.commit()

        print("[MAIN PAGE] Ready")

        # 8. Process discovered pages
        for record in discovered_records:

            try:
                print(
                    f"[PAGE] Processing: {record['url']}"
                )

                page_response = fetch_page(
                    record["url"]
                )

                page_soup = BeautifulSoup(
                    page_response.text,
                    "html.parser"
                )

                page_assets = rewrite_assets(
                    page_soup,
                    record["url"],
                    project_dir,
                    asset_map,
                    project_id
                )

                assets_count += page_assets

                rewrite_page_links(
                    page_soup,
                    record["url"],
                    source_url,
                    main_page_url_map,
                    project_id
                )

                page_path = os.path.join(
                    project_dir,
                    record["file"]
                )

                with open(
                    page_path,
                    "w",
                    encoding="utf-8",
                    errors="ignore"
                ) as file:
                    file.write(str(page_soup))

                internal_title = (
                    page_soup.title.get_text(strip=True)
                    if page_soup.title
                    else record["file"]
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
                    record["id"],
                    project_id,
                    record["url"],
                    record["file"],
                    internal_title,
                    datetime.now().isoformat()
                ))

                pages_created.append({
                    "id": record["id"],
                    "url": record["url"],
                    "file": record["file"],
                    "title": internal_title,
                    "preview_url": (
                        f"/preview/{project_id}/page/"
                        f"{record['id']}"
                    )
                })

                conn.commit()

            except Exception as page_error:
                print(
                    f"[PAGE ERROR] "
                    f"{record['url']}: {page_error}"
                )

        # 9. Update project
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
            assets_count,
            project_id
        ))

        conn.commit()

        print("=" * 60)
        print(f"[SUCCESS] Project ready: {project_id}")
        print(f"[SUCCESS] Pages: {len(pages_created)}")
        print(f"[SUCCESS] Assets: {assets_count}")
        print("=" * 60)

        return jsonify({
            "success": True,
            "project_id": project_id,
            "title": page_title,
            "source_url": source_url,
            "pages_count": len(pages_created),
            "assets_count": assets_count,
            "pages": pages_created,
            "preview_url": f"/preview/{project_id}",
            "first_page_preview": (
                f"/preview/{project_id}/page/{page_id}"
            )
        })

    except requests.exceptions.RequestException as error:

        print(f"[REQUEST ERROR] {error}")

        if project_dir:
            shutil.rmtree(
                project_dir,
                ignore_errors=True
            )

        return jsonify({
            "success": False,
            "error": (
                "Could not open this website. "
                f"Details: {str(error)}"
            )
        }), 500

    except Exception as error:

        print(f"[CRITICAL ERROR] {error}")

        if project_dir:
            shutil.rmtree(
                project_dir,
                ignore_errors=True
            )

        return jsonify({
            "success": False,
            "error": f"Analysis failed: {str(error)}"
        }), 500

    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
