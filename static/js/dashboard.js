document.addEventListener("DOMContentLoaded", () => {

    const analyzeForm =
        document.getElementById("analyzeForm");

    const targetUrl =
        document.getElementById("targetUrl");

    const analyzeBtn =
        document.getElementById("analyzeBtn");

    const projectsGrid =
        document.getElementById("projectsGrid");

    const emptyState =
        document.getElementById("emptyState");

    const resultSection =
        document.getElementById("resultSection");

    const refreshBtn =
        document.getElementById("refreshBtn");

    const aboutBtn =
        document.getElementById("aboutBtn");

    const aboutModal =
        document.getElementById("aboutModal");

    const closeAbout =
        document.getElementById("closeAbout");


    let currentProject = null;


    /* ----------------------------
       PROJECT ANALYSIS
    ----------------------------- */

    analyzeForm.addEventListener("submit", async (event) => {

        event.preventDefault();

        const url = targetUrl.value.trim();

        if (!url) {
            showToast(
                "Please enter a website URL.",
                "error"
            );

            return;
        }

        setLoading(true);

        try {

            const response =
                await fetch("/api/analyze", {

                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({
                        url: url
                    })

                });

            const data =
                await response.json();

            if (!data.success) {
                throw new Error(
                    data.error ||
                    "Website analysis failed."
                );
            }

            currentProject = data;

            renderResult(data);

            targetUrl.value = "";

            showToast(
                "Website analysis completed successfully.",
                "success"
            );

            loadProjects();

        } catch (error) {

            showToast(
                error.message ||
                "Something went wrong.",
                "error"
            );

        } finally {

            setLoading(false);

        }

    });


    /* ----------------------------
       LOADING STATE
    ----------------------------- */

    function setLoading(loading) {

        const btnText =
            analyzeBtn.querySelector(".btn-text");

        const btnLoader =
            analyzeBtn.querySelector(".btn-loader");

        analyzeBtn.disabled = loading;

        btnText.classList.toggle(
            "hidden",
            loading
        );

        btnLoader.classList.toggle(
            "hidden",
            !loading
        );

    }


    /* ----------------------------
       RESULT RENDER
    ----------------------------- */

    function renderResult(data) {

        resultSection.classList.remove(
            "hidden"
        );

        document.getElementById(
            "resultTitle"
        ).textContent =
            data.title ||
            "Website Replica Ready";

        document.getElementById(
            "resultUrl"
        ).textContent =
            data.source_url;

        document.getElementById(
            "resultPages"
        ).textContent =
            data.pages_count;

        document.getElementById(
            "resultAssets"
        ).textContent =
            data.assets_count;


        const previewUrl =
            window.location.origin +
            data.preview_url;


        const openPreviewBtn =
            document.getElementById(
                "openPreviewBtn"
            );

        openPreviewBtn.href =
            data.preview_url;


        const exportBtn =
            document.getElementById(
                "exportBtn"
            );

        exportBtn.href =
            `/api/project/${data.project_id}/export`;


        const copyPreviewBtn =
            document.getElementById(
                "copyPreviewBtn"
            );

        copyPreviewBtn.onclick =
            async () => {

                await copyText(
                    previewUrl
                );

                showToast(
                    "Preview link copied.",
                    "success"
                );

            };


        const deleteBtn =
            document.getElementById(
                "deleteCurrentBtn"
            );

        deleteBtn.onclick =
            () => deleteProject(
                data.project_id,
                true
            );


        const pageList =
            document.getElementById(
                "pageList"
            );

        pageList.innerHTML = "";


        data.pages.forEach(
            (page, index) => {

                const item =
                    document.createElement("a");

                item.className =
                    "page-item";

                item.href =
                    `/preview/${data.project_id}/page/${page.id}`;

                item.target =
                    "_blank";

                item.innerHTML = `
                    <div class="page-number">
                        ${index + 1}
                    </div>

                    <div class="page-info">
                        <strong>
                            ${escapeHtml(page.title)}
                        </strong>

                        <span>
                            ${escapeHtml(page.url)}
                        </span>
                    </div>

                    <i class="fa-solid fa-arrow-up-right-from-square"></i>
                `;

                pageList.appendChild(
                    item
                );

            }
        );


        resultSection.scrollIntoView({
            behavior: "smooth",
            block: "start"
        });

    }


    /* ----------------------------
       PROJECT LIST
    ----------------------------- */

    async function loadProjects() {

        try {

            const response =
                await fetch(
                    "/api/projects"
                );

            const data =
                await response.json();

            if (!data.success) {
                return;
            }

            projectsGrid.innerHTML = "";


            let totalPages = 0;
            let totalAssets = 0;

            data.projects.forEach(
                project => {

                    totalPages +=
                        project.pages_count || 0;

                    totalAssets +=
                        project.assets_count || 0;


                    const card =
                        document.createElement("div");

                    card.className =
                        "project-card";

                    const date =
                        new Date(
                            project.created_at
                        );

                    card.innerHTML = `
                        <div class="project-card-top">

                            <div class="project-icon">
                                <i class="fa-solid fa-globe"></i>
                            </div>

                            <button
                                class="card-delete"
                                title="Delete project">

                                <i class="fa-regular fa-trash-can"></i>

                            </button>

                        </div>

                        <h3>
                            ${escapeHtml(project.title)}
                        </h3>

                        <p class="project-url">
                            ${escapeHtml(project.source_url)}
                        </p>

                        <div class="project-meta">

                            <span>
                                <i class="fa-regular fa-file-lines"></i>
                                ${project.pages_count} Pages
                            </span>

                            <span>
                                <i class="fa-regular fa-image"></i>
                                ${project.assets_count} Assets
                            </span>

                        </div>

                        <div class="project-card-footer">

                            <span>
                                ${date.toLocaleDateString()}
                            </span>

                            <button class="open-project">
                                Open
                                <i class="fa-solid fa-arrow-right"></i>
                            </button>

                        </div>
                    `;


                    card.querySelector(
                        ".open-project"
                    ).addEventListener(
                        "click",
                        () => {
                            openProject(
                                project.id
                            );
                        }
                    );


                    card.querySelector(
                        ".card-delete"
                    ).addEventListener(
                        "click",
                        (event) => {

                            event.stopPropagation();

                            deleteProject(
                                project.id,
                                false
                            );

                        }
                    );


                    projectsGrid.appendChild(
                        card
                    );

                }
            );


            emptyState.classList.toggle(
                "hidden",
                data.projects.length > 0
            );


            document.getElementById(
                "projectCount"
            ).textContent =
                data.projects.length;


            document.getElementById(
                "pageCount"
            ).textContent =
                totalPages;


            document.getElementById(
                "assetCount"
            ).textContent =
                totalAssets;


        } catch (error) {

            console.error(
                "Could not load projects:",
                error
            );

        }

    }


    /* ----------------------------
       OPEN PROJECT
    ----------------------------- */

    async function openProject(
        projectId
    ) {

        try {

            const response =
                await fetch(
                    `/api/project/${projectId}`
                );

            const data =
                await response.json();

            if (!data.success) {
                throw new Error(
                    data.error
                );
            }


            currentProject = {
                project_id:
                    projectId,

                title:
                    data.project.title,

                source_url:
                    data.project.source_url,

                pages_count:
                    data.project.pages_count,

                assets_count:
                    data.project.assets_count,

                pages:
                    data.pages,

                preview_url:
                    `/preview/${projectId}`
            };


            renderResult(
                currentProject
            );

        } catch (error) {

            showToast(
                "Could not open this project.",
                "error"
            );

        }

    }


    /* ----------------------------
       DELETE PROJECT
    ----------------------------- */

    async function deleteProject(
        projectId,
        isCurrent
    ) {

        const confirmed =
            confirm(
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
                        method:
                            "DELETE"
                    }
                );

            const data =
                await response.json();

            if (!data.success) {
                throw new Error();
            }


            if (isCurrent) {

                resultSection.classList.add(
                    "hidden"
                );

                currentProject = null;

            }


            showToast(
                "Project deleted.",
                "success"
            );

            loadProjects();


        } catch (error) {

            showToast(
                "Could not delete the project.",
                "error"
            );

        }

    }


    /* ----------------------------
       REFRESH
    ----------------------------- */

    refreshBtn.addEventListener(
        "click",
        () => {

            refreshBtn.classList.add(
                "rotating"
            );

            loadProjects().finally(
                () => {

                    setTimeout(
                        () => {
                            refreshBtn.classList.remove(
                                "rotating"
                            );
                        },
                        500
                    );

                }
            );

        }
    );


    /* ----------------------------
       ABOUT MODAL
    ----------------------------- */

    aboutBtn.addEventListener(
        "click",
        () => {

            aboutModal.classList.remove(
                "hidden"
            );

        }
    );


    closeAbout.addEventListener(
        "click",
        closeAboutModal
    );


    aboutModal.addEventListener(
        "click",
        (event) => {

            if (
                event.target ===
                aboutModal
            ) {
                closeAboutModal();
            }

        }
    );


    function closeAboutModal() {

        aboutModal.classList.add(
            "hidden"
        );

    }


    /* ----------------------------
       COPY
    ----------------------------- */

    async function copyText(text) {

        if (
            navigator.clipboard &&
            window.isSecureContext
        ) {

            await navigator.clipboard.writeText(
                text
            );

            return;
        }


        const textarea =
            document.createElement(
                "textarea"
            );

        textarea.value =
            text;

        document.body.appendChild(
            textarea
        );

        textarea.select();

        document.execCommand(
            "copy"
        );

        textarea.remove();

    }


    /* ----------------------------
       TOAST
    ----------------------------- */

    function showToast(
        message,
        type = "success"
    ) {

        const container =
            document.getElementById(
                "toastContainer"
            );

        const toast =
            document.createElement(
                "div"
            );

        toast.className =
            `toast-message ${type}`;

        toast.innerHTML = `
            <i class="${
                type === "success"
                    ? "fa-solid fa-circle-check"
                    : "fa-solid fa-circle-exclamation"
            }"></i>

            <span>
                ${escapeHtml(message)}
            </span>
        `;

        container.appendChild(
            toast
        );


        setTimeout(
            () => {

                toast.classList.add(
                    "toast-hide"
                );

                setTimeout(
                    () => toast.remove(),
                    250
                );

            },
            3500
        );

    }


    function escapeHtml(value) {

        const div =
            document.createElement(
                "div"
            );

        div.textContent =
            value || "";

        return div.innerHTML;

    }


    loadProjects();

});
