/* Floating AI Assistant chat widget for the dashboard. */
(function () {
  "use strict";

  var API = "/api/v1/assistant/chat";
  var isOpen = false;
  var busy = false;
  var chatHistory = [];

  function $(id) {
    return document.getElementById(id);
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function addMessage(role, text, badges) {
    var history = $("assistant-chat-history");
    var message = document.createElement("div");
    message.className = "assistant-message " + role;

    var bubble = document.createElement("div");
    bubble.className = "assistant-bubble";
    bubble.textContent = text;

    message.appendChild(bubble);

    if (badges && badges.length) {
      var badgeRow = document.createElement("div");
      badgeRow.className = "assistant-badges";

      badges.forEach(function (badge) {
        var item = document.createElement("span");
        item.className = "assistant-badge " + (badge.className || "");
        item.textContent = badge.text;
        badgeRow.appendChild(item);
      });

      message.appendChild(badgeRow);
    }

    history.appendChild(message);
    history.scrollTop = history.scrollHeight;
  }

  function setBusy(value) {
    busy = value;
    $("assistant-chat-send").disabled = value;
    $("assistant-chat-status").textContent = value
      ? "Thinking…"
      : "";
  }

  function sendMessage() {
    var question = $("assistant-chat-input").value.trim();

    if (!question || busy) return;

    var scenario = $("assistant-chat-scenario").value;

    if (scenario === "custom") {
      scenario = $("assistant-chat-custom-scenario").value.trim();

      if (!scenario) {
        addMessage(
          "assistant",
          "Please enter a custom scenario name first.",
          [{ text: "Input needed", className: "validation-failed" }]
        );
        return;
      }
    }

    var hours = Number($("assistant-chat-hours").value);
    var model = $("assistant-chat-model").value;

    addMessage("user", question);
    chatHistory.push({
      role: "user",
      content: question
    });

    $("assistant-chat-input").value = "";
    setBusy(true);

    fetch(API, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        question: question,
        building_id: 1,
        scenario: scenario,
        hours: hours,
        model: model,
        history: chatHistory.slice(-8)
      })
    })
      .then(function (response) {
        if (!response.ok) {
          return response.json().then(function (error) {
            throw new Error(
              error.detail || "Assistant request failed."
            );
          });
        }
        return response.json();
      })
      .then(function (data) {
        var badges = [
          {
            text: data.tool_used || "No tool",
            className: "tool"
          },
          {
            text: data.model_used,
            className: "model"
          },
          {
            text: data.language === "ar" ? "Arabic" : "English",
            className: "language"
          },
          {
            text: data.ai_source === "llm"
              ? "AI answer"
              : "Safe fallback",
            className: data.ai_source === "llm"
              ? "ai-live"
              : "ai-fallback"
          }
        ];

        if (!data.validation.passed) {
          badges.push({
            text: "Validation failed",
            className: "validation-failed"
          });
        }

        addMessage("assistant", data.answer, badges);
        chatHistory.push({
          role: "assistant",
          content: data.answer
        });
      })
      .catch(function (error) {
        addMessage(
          "assistant",
          "Unable to answer: " + error.message,
          [{ text: "Error", className: "validation-failed" }]
        );
      })
      .finally(function () {
        setBusy(false);
      });
  }

  function toggleChat() {
    isOpen = !isOpen;
    $("assistant-chat-panel").hidden = !isOpen;
    $("assistant-chat-toggle").setAttribute(
      "aria-expanded",
      isOpen ? "true" : "false"
    );

    if (isOpen) {
      $("assistant-chat-input").focus();
    }
  }

  function init() {
    $("assistant-chat-scenario").addEventListener("change", function () {
      $("assistant-custom-scenario-label").hidden =
        $("assistant-chat-scenario").value !== "custom";
    });

    $("assistant-chat-toggle").addEventListener("click", toggleChat);
    $("assistant-chat-close").addEventListener("click", toggleChat);
    $("assistant-chat-send").addEventListener("click", sendMessage);

    $("assistant-chat-input").addEventListener(
      "keydown",
      function (event) {
        if (event.key === "Enter") {
          event.preventDefault();
          sendMessage();
        }
      }
    );

    addMessage(
      "assistant",
      "Hello. Ask me anything about the building. I can check status, " +
        "faults, alerts, CCTV, network issues, priorities, and energy data."
    );
  }

  document.addEventListener("DOMContentLoaded", init);
})();