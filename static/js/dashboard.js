document.addEventListener("DOMContentLoaded", () => {
    const analyzeForm = document.getElementById("analyze-form");
    const websiteUrl = document.getElementById("website-url");
    const analyzeButton = document.getElementById("analyze-btn");
    const buttonText = document.getElementById("button-text");
    const loader = document.getElementById("loader");
    const resultBox = document.getElementById("result-box");
    const toast = document.getElementById("toast");

    let currentProjectId = null;

    if (!analyzeForm) {
        console.error("ERROR: analyze-form not found.");
        return;
    }

    function showToast(message, isError = false) {
        if (!toast) {
            alert(message);
            return;
        }

        toast.textContent = message;
        toast.className = isError
            ? "toast error show"
            : "toast show";

        clearTimeout(window.shadowNetToastTimer);

        window.shadowNetToastTimer = setTimeout(() => {
            toast.className = "toast";
        }, 5000);
    }

    function setLoading(loading) {
        if (analyzeButton) {
            analyzeButton.disabled = loading;
        }

        if (loader) {
            loader.classList.toggle("show", loading);
        }

        if (buttonText) {
            buttonText.textContent = loading
                ? "Analyzing..."
                : "Analyze Site";
        }
    }

    async function readJsonResponse(response) {
        const contentType =
            response.headers.get("content-type") || "";

        const text = await response.text();

        if (!text) {
            return {};
        }

        if (contentType.includes("application/json")) {
            try {
                return JSON.parse(text);
            } catch (error) {
                console.error("Invalid JSON:", error);
                throw new Error(
                    "Server returned an invalid JSON response."
                );
            }
        }

        console.error("Non-JSON server response:", text);

        throw new Error(
            "Server error occurred. Check the terminal for details."
        );
    }

    analyzeForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        event.stopPropagation();

        let url = websiteUrl.value.trim();

        if (!url) {
            showToast(
                "Please enter a website URL.",
                true
            );
            return;
        }

        // User agar example.com likhe to automatically https add ho
        if (!/^https?:\/\//i.test(url)) {
            url = "https://" + url;
            websiteUrl.value = url;
        }

        resultBox?.classList.remove("show");
        setLoading(true);

        try {
            console.log(
                "Sending analyze request:",
                url
            );

            const response = await fetch(
                "/api/analyze",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json",
                        "Accept":
                            "application/json"
                    },

                    body: JSON.stringify({
                        url: url
                    })
                }
            );

            const data =
                await readJsonResponse(response);

            console.log(
                "Analyze response:",
                data
            );

            if (!response.ok || !data.success) {
                throw new Error(
                    data.error ||
                    `Analysis failed (HTTP ${response.status}).`
                );
            }

            if (!data.project_id) {
                throw new Error(
                    "Server did not return a project ID."
                );
            }

            currentProjectId = data.project_id;

            // Result title
            const resultTitle =
                document.getElementById("result-title");

            if (resultTitle) {
                resultTitle.textContent =
                    data.title ||
                    "Project ready";
            }

            // Result description
            const resultDescription =
                document.getElementById(
                    "result-description"
                );

            if (resultDescription) {
                resultDescription.textContent =
                    data.description ||
                    "Website replica project created successfully.";
            }

            // Pages count
            const resultPages =
                document.getElementById("result-pages");

            if (resultPages) {
                resultPages.textContent =
                    data.pages_count ?? 0;
            }

            // Assets count
            const resultAssets =
                document.getElementById("result-assets");

            if (resultAssets) {
                resultAssets.textContent =
                    data.assets_count ?? 0;
            }

            // Preview URL
            const previewUrl =
                data.preview_url ||
                `/preview/${currentProjectId}`;

            const previewButton =
                document.getElementById("preview-btn");

            if (previewButton) {
                previewButton.href = previewUrl;
            }

            // First page preview
            const directPreviewButton =
                document.getElementById(
                    "direct-preview-btn"
                );

            const firstPagePreview =
                data.first_page_preview ||
                (
                    Array.isArray(data.pages) &&
                    data.pages.length > 0
                        ? data.pages[0].preview_url
                        : null
                );

            if (directPreviewButton) {
                if (firstPagePreview) {
                    directPreviewButton.href =
                        firstPagePreview;

                    directPreviewButton.style.display =
                        "inline-flex";
                } else {
                    directPreviewButton.style.display =
                        "none";
                }
            }

            // Export
            const exportButton =
                document.getElementById("export-btn");

            if (exportButton) {
                exportButton.href =
                    `/api/project/${currentProjectId}/export`;
            }

            // Delete
            const deleteButton =
                document.getElementById(
                    "delete-current-btn"
                );

            if (deleteButton) {
                deleteButton.dataset.projectId =
                    currentProjectId;
            }

            // Show result
            if (resultBox) {
                resultBox.classList.add("show");

                setTimeout(() => {
                    resultBox.scrollIntoView({
                        behavior: "smooth",
                        block: "center"
                    });
                }, 150);
            }

            showToast(
                "Project created successfully."
            );

            if (
                typeof loadProjects === "function"
            ) {
                loadProjects();
            }

        } catch (error) {
            console.error(
                "ShadowNet analyze error:",
                error
            );

            showToast(
                error.message ||
                "Something went wrong.",
                true
            );

        } finally {
            setLoading(false);
        }
    });

    // Delete current project
    const deleteCurrentButton =
        document.getElementById(
            "delete-current-btn"
        );

    if (deleteCurrentButton) {
        deleteCurrentButton.addEventListener(
            "click",
            async () => {
                const projectId =
                    currentProjectId ||
                    deleteCurrentButton.dataset.projectId;

                if (!projectId) {
                    showToast(
                        "No project selected.",
                        true
                    );
                    return;
                }

                const confirmed = confirm(
                    "Delete this project permanently?"
                );

                if (!confirmed) {
                    return;
                }

                try {
                    const response =
                        await fetch(
                            `/api/project/${projectId}`,
                            {
                                method: "DELETE"
                            }
                        );

                    const data =
                        await readJsonResponse(
                            response
                        );

                    if (
                        !response.ok ||
                        !data.success
                    ) {
                        throw new Error(
                            data.error ||
                            "Could not delete project."
                        );
                    }

                    currentProjectId = null;

                    resultBox?.classList.remove(
                        "show"
                    );

                    showToast(
                        "Project deleted successfully."
                    );

                    if (
                        typeof loadProjects ===
                        "function"
                    ) {
                        loadProjects();
                    }

                } catch (error) {
                    console.error(error);

                    showToast(
                        error.message ||
                        "Could not delete project.",
                        true
                    );
                }
            }
        );
    }

    // Projects list
    async function loadProjects() {
        const container =
            document.getElementById(
                "projects-list"
            );

        if (!container) {
            return;
        }

        try {
            const response =
                await fetch("/api/projects");

            const data =
                await readJsonResponse(response);

            if (
                !response.ok ||
                !data.success
            ) {
                throw new Error(
                    data.error ||
                    "Could not load projects."
                );
            }

            const projects =
                data.projects || [];

            if (!projects.length) {
                container.innerHTML = `
                    <div class="empty-state">
                        No projects yet. Analyze an authorized website to begin.
                    </div>
                `;
                return;
            }

            container.innerHTML =
                projects.map((project) => {
                    const title =
                        escapeHtml(
                            project.title ||
                            "Untitled Website"
                        );

                    const sourceUrl =
                        escapeHtml(
                            project.source_url ||
                            ""
                        );

                    const pageCount =
                        project.pages_count ?? 0;

                    const previewUrl =
                        project.preview_url ||
                        `/preview/${project.id}`;

                    return `
                        <div class="project">
                            <div class="project-main">
                                <h3 class="project-title">
                                    ${title}
                                </h3>

                                <div class="project-url">
                                    ${sourceUrl}
                                </div>
                            </div>

                            <div class="project-meta">
                                <span>
                                    ${pageCount} page(s)
                                </span>

                                <a
                                    href="${previewUrl}"
                                    target="_blank"
                                    class="project-preview-btn"
                                >
                                    Open Preview
                                </a>
                            </div>
                        </div>
                    `;
                }).join("");

        } catch (error) {
            console.error(
                "Projects load error:",
                error
            );

            container.innerHTML = `
                <div class="empty-state">
                    Could not load projects.
                </div>
            `;
        }
    }

    function escapeHtml(value) {
        const div =
            document.createElement("div");

        div.textContent =
            value ?? "";

        return div.innerHTML;
    }

    // Initial projects load
    loadProjects();
});
