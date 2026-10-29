(() => {
  const input = document.getElementById("question-input");
  const conversation = document.getElementById("conversation");
  const sendButton = document.getElementById("send-button");

  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function appendUserMessage(question) {
    const message = node("article", "message user");
    const bubble = node("div", "user-bubble", question);
    message.appendChild(bubble);
    conversation.appendChild(message);
  }

  function appendPending() {
    const message = node("article", "message");
    message.id = "pending-answer";
    message.innerHTML = `
      <div class="message-avatar">
        <svg class="icon"><use href="#i-bot"></use></svg>
      </div>
      <div class="message-body">
        <div class="message-meta">
          <strong>知问 Agent</strong>
          <span class="route-tag">执行中</span>
          <time>刚刚</time>
        </div>
        <div class="answer"><p>正在检索知识库并生成回答…</p></div>
      </div>`;
    conversation.appendChild(message);
    return message;
  }

  function appendAnswer(result) {
    const message = node("article", "message");
    const citations = (result.citations || [])
      .map((item) => `<button class="citation-link" type="button">${item.index}</button>`)
      .join("");
    const tools = (result.tool_calls || [])
      .map(
        (item) =>
          `<div class="answer-note"><svg class="icon"><use href="#i-zap"></use></svg>${item.tool_name} · ${item.status}</div>`,
      )
      .join("");

    message.innerHTML = `
      <div class="message-avatar">
        <svg class="icon"><use href="#i-bot"></use></svg>
      </div>
      <div class="message-body">
        <div class="message-meta">
          <strong>知问 Agent</strong>
          <span class="route-tag">${result.route || "knowledge"}</span>
          <time>刚刚</time>
        </div>
        <div class="answer">
          <p></p>
          ${tools}
          <div class="retrieval-summary">
            <span class="step">引用 <strong>${(result.citations || []).length}</strong></span>
            <span class="arrow">·</span>
            <span class="step">耗时 <strong>${result.latency_ms || 0} ms</strong></span>
            <span class="arrow">·</span>
            <span class="step">Trace <strong>${result.trace_id || "-"}</strong></span>
          </div>
        </div>
      </div>`;
    message.querySelector(".answer p").textContent = result.answer || "";
    if (citations) {
      const paragraph = message.querySelector(".answer p");
      paragraph.insertAdjacentHTML("beforeend", ` ${citations}`);
    }
    conversation.appendChild(message);
  }

  function appendError(error) {
    const message = node("article", "message");
    message.innerHTML = `
      <div class="message-avatar">
        <svg class="icon"><use href="#i-bot"></use></svg>
      </div>
      <div class="message-body">
        <div class="message-meta"><strong>知问 Agent</strong><span class="route-tag">错误</span></div>
        <div class="answer"><div class="answer-note"></div></div>
      </div>`;
    message.querySelector(".answer-note").textContent =
      error?.message || "请求失败，请稍后重试";
    conversation.appendChild(message);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function formatTime(value) {
    try {
      return new Date(value).toLocaleString("zh-CN", { hour12: false });
    } catch {
      return value || "-";
    }
  }

  window.demoLoadDocuments = async function () {
    const tableBody = document.querySelector("#view-knowledge tbody");
    const metricValues = document.querySelectorAll("#view-knowledge .metric-value");
    if (!tableBody) return;

    try {
      const response = await fetch("/api/v1/documents");
      const body = await response.json();
      const documents = body.documents || [];
      const chunks = documents.reduce((sum, item) => sum + Number(item.chunk_count || 0), 0);
      if (metricValues[0]) metricValues[0].textContent = String(documents.length);
      if (metricValues[1]) metricValues[1].textContent = String(chunks);
      if (metricValues[2]) metricValues[2].textContent = String(chunks);
      const latest = documents.map((item) => item.updated_at).sort().at(-1);
      if (metricValues[3] && latest) metricValues[3].textContent = formatTime(latest);
      const knowledgeCount = document.querySelector('.nav-button[data-view="knowledge"] .count');
      if (knowledgeCount) knowledgeCount.textContent = String(documents.length);
      const workspaceMeta = document.querySelector(".workspace-label span");
      if (workspaceMeta) workspaceMeta.textContent = `演示空间 · ${documents.length} 个文档`;

      tableBody.innerHTML = documents.map((item) => {
        const isPdf = item.file_type === "pdf";
        const iconClass = isPdf ? "file-icon pdf" : item.file_type === "markdown" ? "file-icon md" : "file-icon";
        return `
          <tr>
            <td>
              <div class="document-cell">
                <div class="${iconClass}"><svg class="icon"><use href="#i-file"></use></svg></div>
                <div><strong>${escapeHtml(item.filename)}</strong><span>${escapeHtml(item.file_type)} · ${escapeHtml(item.page_count)} 页</span></div>
              </div>
            </td>
            <td><span class="status ready">处理完成</span></td>
            <td>${escapeHtml(item.chunk_count)}</td>
            <td>${escapeHtml(formatTime(item.updated_at))}</td>
            <td><div class="row-actions"><button class="icon-button" title="更多操作" type="button"><svg class="icon"><use href="#i-more"></use></svg></button></div></td>
          </tr>`;
      }).join("");
    } catch {
      tableBody.innerHTML = '<tr><td colspan="5">知识库加载失败</td></tr>';
    }
  };

  const uploadZone = document.querySelector(".upload-zone");
  if (uploadZone) {
    const fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.accept = ".txt,.md,.markdown,.pdf";
    fileInput.hidden = true;
    document.body.appendChild(fileInput);
    uploadZone.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", async () => {
      const file = fileInput.files?.[0];
      if (!file) return;
      const formData = new FormData();
      formData.append("file", file);
      try {
        const response = await fetch("/api/v1/documents", { method: "POST", body: formData });
        if (!response.ok) throw new Error("上传失败");
        await window.demoLoadDocuments();
      } catch (error) {
        alert(error.message || "上传失败");
      } finally {
        fileInput.value = "";
      }
    });
  }

  window.demoLoadTrace = async function () {
    const runId = localStorage.getItem("lastRunId");
    if (!runId) return;
    try {
      const response = await fetch(`/api/v1/runs/${encodeURIComponent(runId)}`);
      const body = await response.json();
      const run = body.run || {};
      const metrics = document.querySelectorAll("#view-trace .metric-value");
      if (metrics[0]) metrics[0].textContent = `${Math.round(Number(run.latency_ms || 0) / 100) / 10}`;
      if (metrics[1]) metrics[1].textContent = String((run.retrieval_logs || []).length);
      if (metrics[2]) metrics[2].textContent = String((run.tool_calls || []).length);
    } catch {
      // Keep the prototype trace visible if the run is unavailable.
    }
  };

  window.demoSendQuestion = async function () {
    const question = input.value.trim();
    if (!question) return;

    input.value = "";
    appendUserMessage(question);
    const pending = appendPending();
    conversation.scrollTop = conversation.scrollHeight;
    sendButton.disabled = true;

    try {
      const response = await fetch("/api/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      const body = await response.json();
      pending.remove();
      if (!response.ok) {
        appendError(body.error);
        return;
      }
      localStorage.setItem("lastRunId", body.run_id || "");
      appendAnswer(body);
    } catch (error) {
      pending.remove();
      appendError({ message: error.message });
    } finally {
      sendButton.disabled = false;
      conversation.scrollTop = conversation.scrollHeight;
      input.focus();
    }
  };
})();

window.demoLoadDocuments();
