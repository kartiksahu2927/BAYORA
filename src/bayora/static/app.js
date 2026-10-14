const particlePalettes = {
  red: ["#f04a5f", "#ff7a68", "#be2948", "#ffb06c"],
  blue: ["#4ca7ff", "#78c5ff", "#2d65cb", "#b8edff"],
  neutral: ["#56a6aa", "#90aeb4", "#637487", "#c8d8d8"],
};

function hexToRgb(hex) {
  const value = hex.replace("#", "");
  return [parseInt(value.slice(0, 2), 16), parseInt(value.slice(2, 4), 16), parseInt(value.slice(4, 6), 16)];
}

function mixHex(from, to, amount) {
  const a = hexToRgb(from);
  const b = hexToRgb(to);
  return `rgb(${a.map((channel, index) => Math.round(channel + (b[index] - channel) * amount)).join(" ")})`;
}

class ParticleField {
  constructor(canvas) {
    this.canvas = canvas;
    this.context = canvas?.getContext("2d");
    this.particles = [];
    this.width = 0;
    this.height = 0;
    this.frame = null;
    this.lastTime = 0;
    this.visible = !document.hidden;
    this.reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches || false;
    this.role = "admin";
    this.colors = particlePalettes.neutral;
    this.previousColors = this.colors;
    this.colorStarted = performance.now();
    if (!this.context) return;
    this.resize = this.resize.bind(this);
    this.handleVisibility = this.handleVisibility.bind(this);
    window.addEventListener("resize", this.resize, { passive: true });
    document.addEventListener("visibilitychange", this.handleVisibility);
    this.resize();
    this.seed();
    if (this.reducedMotion) this.draw(performance.now());
    else this.animate(performance.now());
  }

  paletteFor(role) {
    return particlePalettes[role] || particlePalettes.neutral;
  }

  setRole(role) {
    if (!this.context) return;
    const nextRole = role === "red" || role === "blue" ? role : "neutral";
    if (nextRole === this.role) return;
    this.role = nextRole;
    this.previousColors = this.colors;
    this.colors = this.paletteFor(nextRole);
    this.colorStarted = performance.now();
    if (this.reducedMotion) this.draw(performance.now());
  }

  particleCount() {
    const areaCount = Math.round((this.width * this.height) / 30000);
    return Math.min(this.width < 650 ? 30 : 70, Math.max(this.width < 650 ? 16 : 35, areaCount));
  }

  createParticle(initial = false) {
    const speed = 18 + Math.random() * 34;
    const angle = -0.58 + (Math.random() - 0.5) * 0.3;
    const size = .65 + Math.random() * 2.35;
    const particle = {
      x: initial ? Math.random() * this.width : -10 - Math.random() * 100,
      y: initial ? Math.random() * this.height : this.height * (.45 + Math.random() * .7),
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      size,
      trail: .12 + Math.random() * .28,
      life: 3 + Math.random() * 6,
      age: initial ? Math.random() * 6 : 0,
      alpha: .26 + Math.random() * .58,
      tone: Math.floor(Math.random() * 4),
      bright: Math.random() > .82,
    };
    return particle;
  }

  seed() {
    if (!this.context) return;
    this.particles = Array.from({ length: this.particleCount() }, () => this.createParticle(true));
  }

  resize() {
    if (!this.context) return;
    this.width = window.innerWidth;
    this.height = window.innerHeight;
    const pixelRatio = Math.min(window.devicePixelRatio || 1, 1.5);
    this.canvas.width = Math.max(1, Math.floor(this.width * pixelRatio));
    this.canvas.height = Math.max(1, Math.floor(this.height * pixelRatio));
    this.canvas.style.width = `${this.width}px`;
    this.canvas.style.height = `${this.height}px`;
    this.context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
    const count = this.particleCount();
    if (this.particles.length > count) this.particles.length = count;
    while (this.particles.length < count) this.particles.push(this.createParticle(true));
    if (this.reducedMotion) this.draw(performance.now());
  }

  handleVisibility() {
    this.visible = !document.hidden;
    if (this.visible && !this.reducedMotion) {
      this.lastTime = performance.now();
      this.animate(this.lastTime);
    } else if (!this.visible && this.frame) {
      cancelAnimationFrame(this.frame);
      this.frame = null;
    }
  }

  animate(time) {
    if (!this.context || !this.visible || this.reducedMotion) return;
    this.draw(time);
    this.frame = requestAnimationFrame((nextTime) => this.animate(nextTime));
  }

  draw(time) {
    if (!this.context) return;
    const elapsed = this.lastTime ? Math.min((time - this.lastTime) / 1000, .05) : 0;
    this.lastTime = time;
    const colorProgress = Math.min(1, (time - this.colorStarted) / 650);
    const context = this.context;
    context.clearRect(0, 0, this.width, this.height);
    context.globalCompositeOperation = "lighter";
    this.particles.forEach((particle) => {
      if (!this.reducedMotion) {
        particle.x += particle.vx * elapsed;
        particle.y += particle.vy * elapsed;
        particle.age += elapsed;
      }
      if (particle.x > this.width + 40 || particle.y < -40 || particle.age > particle.life) {
        Object.assign(particle, this.createParticle(false));
      }
      const edgeFade = Math.min(1, particle.age * 2.4, (particle.life - particle.age) * 2.4);
      const alpha = Math.max(0, particle.alpha * edgeFade);
      const color = mixHex(this.previousColors[particle.tone], this.colors[particle.tone], colorProgress);
      context.globalAlpha = alpha * .32;
      context.strokeStyle = color;
      context.lineWidth = Math.max(.5, particle.size * .55);
      context.beginPath();
      context.moveTo(particle.x - particle.vx * particle.trail, particle.y - particle.vy * particle.trail);
      context.lineTo(particle.x, particle.y);
      context.stroke();
      context.globalAlpha = alpha * (particle.bright ? .72 : .45);
      context.fillStyle = color;
      context.beginPath();
      context.arc(particle.x, particle.y, particle.size * (particle.bright ? 1.25 : 1), 0, Math.PI * 2);
      context.fill();
      if (particle.bright) {
        context.globalAlpha = alpha * .16;
        context.beginPath();
        context.arc(particle.x, particle.y, particle.size * 3.2, 0, Math.PI * 2);
        context.fill();
      }
    });
    context.globalAlpha = 1;
    context.globalCompositeOperation = "source-over";
  }

  destroy() {
    if (this.frame) cancelAnimationFrame(this.frame);
    window.removeEventListener("resize", this.resize);
    document.removeEventListener("visibilitychange", this.handleVisibility);
  }
}

const roleProfiles = {
  red: {
    name: "RED TEAM",
    workspace: "Adversarial Evaluation Workspace",
    eyebrow: "ADVERSARIAL TESTING / CONTROLLED ATTACK SURFACE",
    title: "Probe the boundary.<br><span>Expose the failure.</span>",
    copy: "Run controlled attack simulations against the target model while Bayora preserves tenant, session, policy, and audit boundaries.",
    validationEyebrow: "ATTACK SURFACE CHECK",
    validationTitle: "Security Validation",
    validationCopy: "Review the controls that contain adversarial input, protect private data, and preserve audit integrity.",
    evaluationEyebrow: "RED TEAM WORKSPACE",
    evaluationTitle: "New Evaluation",
    evaluationPill: "isolated session",
    promptLabel: "Attack / evaluation input",
    promptPlaceholder: "Describe a controlled behavior probe for the model...",
    evaluationHint: "Input is hashed for audit provenance.",
    evaluationButton: "Start evaluation",
    sessionsEyebrow: "PROVENANCE / ATTACK SURFACE",
    sessionsTitle: "Evaluation Sessions",
    auditEyebrow: "INTEGRITY MONITOR",
    auditTitle: "Audit Chain",
    canCreate: true,
    canReview: false,
  },
  blue: {
    name: "BLUE TEAM",
    workspace: "Defensive Security Workspace",
    eyebrow: "DEFENSE / MONITORING / SECURITY RESPONSE",
    title: "Watch the boundary.<br><span>Protect the system.</span>",
    copy: "Review assessments explicitly shared with your account, then analyze the recorded evidence from the defensive side of the Bayora control plane.",
    validationEyebrow: "DEFENSIVE CONTROLS",
    validationTitle: "Policy & Detection",
    validationCopy: "Review policy enforcement, blocked information flows, and the integrity signals available to the defense team.",
    evaluationEyebrow: "DEFENSIVE CONTROLS",
    evaluationTitle: "Analyze Recorded Findings",
    evaluationPill: "advisory / unverified",
    promptLabel: "Evaluation input",
    promptPlaceholder: "Red Team authorization is required to create an evaluation.",
    evaluationHint: "Red Team creates assessments; Blue Team analyzes explicitly shared evidence.",
    evaluationButton: "Red Team only",
    sessionsEyebrow: "SECURITY EVENTS / MONITORING",
    sessionsTitle: "Authorized Evaluation Sessions",
    auditEyebrow: "EVIDENCE ACCESS",
    auditTitle: "Audit Chain",
    canCreate: false,
    canReview: false,
  },
  admin: {
    name: "SECURITY ADMINISTRATOR",
    workspace: "Control & Policy Workspace",
    eyebrow: "CONTROL PLANE / SECURITY CONFIGURATION",
    title: "Operate the boundary.<br><span>Keep it verifiable.</span>",
    copy: "Inspect provider status, policy controls, validation results, and the tenant-scoped evaluation system from the control plane.",
    validationEyebrow: "RUNTIME & POLICY STATUS",
    validationTitle: "Security Validation",
    validationCopy: "Exercise policy enforcement, the isolated model worker, and audit integrity from one reproducible run.",
    evaluationEyebrow: "CONTROL PLANE",
    evaluationTitle: "Policies & Access Control",
    evaluationPill: "review access",
    promptLabel: "Evaluation input",
    promptPlaceholder: "Evaluation creation is restricted to the Red Team role.",
    evaluationHint: "Use the Red Team role to submit a controlled evaluation.",
    evaluationButton: "Red Team only",
    sessionsEyebrow: "RUNTIME PROVENANCE",
    sessionsTitle: "Evaluation Sessions",
    auditEyebrow: "INTEGRITY MONITOR",
    auditTitle: "Audit Chain",
    canCreate: false,
    canReview: true,
  },
  auditor: {
    name: "AUDITOR",
    workspace: "Evidence & Provenance Workspace",
    eyebrow: "AUDIT / PROVENANCE / INTEGRITY",
    title: "Follow the evidence.<br><span>Verify every decision.</span>",
    copy: "Review evaluation history, provider provenance, lifecycle events, and the integrity of Bayora's signed audit chain.",
    validationEyebrow: "EVIDENCE REVIEW",
    validationTitle: "Audit Validation",
    validationCopy: "Run the reproducible controls and inspect the signed event sequence without changing the evaluated data.",
    evaluationEyebrow: "EVIDENCE REVIEW",
    evaluationTitle: "Evidence Scope & Findings",
    evaluationPill: "review access",
    promptLabel: "Evaluation input",
    promptPlaceholder: "Evaluation creation is restricted to the Red Team role.",
    evaluationHint: "Use the Red Team role to submit a controlled evaluation.",
    evaluationButton: "Red Team only",
    sessionsEyebrow: "EVIDENCE / PROVENANCE",
    sessionsTitle: "Evaluation Sessions",
    auditEyebrow: "SIGNED EVIDENCE",
    auditTitle: "Audit Chain",
    canCreate: false,
    canReview: true,
  },
};

const roleUsernames = {
  red: "red-analyst",
  blue: "blue-engineer",
  admin: "security-admin",
  auditor: "audit-reviewer",
};

const state = {
  role: "admin",
  actorId: null,
  authenticated: false,
  authenticationRequest: null,
  switchingRole: false,
  sessionsRefreshing: false,
  sessionsLoaded: false,
  evaluations: [],
  roleVersion: 0,
  sessionRequest: null,
  auditRequest: null,
  creatingEvaluation: false,
  validating: false,
  assessmentVersion: 0,
  assessmentController: null,
  selectedEvaluationId: "",
  selectedEvaluation: null,
  assessmentLoading: false,
  historiesLoading: false,
  historiesRequest: null,
  pendingAssessmentAction: "",
  recipients: [],
};

const $ = (id) => document.getElementById(id);
const particleField = new ParticleField($("particle-canvas"));
window.addEventListener("pagehide", () => particleField.destroy(), { once: true });

async function api(path, options = {}) {
  const { allowEmptyResponse = false, ...fetchOptions } = options;
  let response;
  try {
    response = await fetch(path, {
      cache: "no-store",
      credentials: "same-origin",
      ...fetchOptions,
      headers: { "Content-Type": "application/json", ...(fetchOptions.headers || {}) },
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error("Unable to reach Bayora. Check your connection and try again.");
  }
  const data = await response.json().catch(() => null);
  if (response.ok && data === null && allowEmptyResponse) return {};
  if (!response.ok || data === null) {
    const fallback = response.status === 401
      ? "Your Bayora session is not authenticated. Please sign in again."
      : response.status === 403
        ? "Your account is authenticated, but this action is not allowed for its role."
        : response.ok
          ? "Bayora returned an invalid response."
          : `Bayora rejected the request (HTTP ${response.status}).`;
    const error = new Error(data?.error || fallback);
    error.status = response.status;
    throw error;
  }
  return data;
}

function formatTime(value) {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character]);
}

function textElement(tag, className, text) {
  const element = document.createElement(tag);
  element.className = className;
  element.textContent = text ?? "";
  return element;
}

function setMessage(id, text, error = false) {
  $(id).className = error ? "message error" : "message";
  $(id).textContent = text;
  if (id !== "evaluation-message") $(id).hidden = !text;
}

function canReadBlueHistory() {
  return ["blue", "admin", "auditor"].includes(state.role);
}

function canShareAssessment() {
  return Boolean(state.selectedEvaluation && isTerminalAssessment(state.selectedEvaluation) && (state.role === "admin"
    || (state.role === "red" && state.actorId && state.selectedEvaluation.actor_id === state.actorId)));
}

function isTerminalAssessment(evaluation) {
  return ["completed", "blocked", "failed"].includes(evaluation?.state);
}

function isFixtureEvidence(evaluation) {
  return evaluation.model?.provider === "fixture" || evaluation.model?.evidence_type === "test_fixture"
    || isFixtureType(evaluation.evidence?.source_evidence_type) || isFixtureType(evaluation.evidence?.evidence_type);
}

function isFixtureType(value) {
  return value === "test_fixture" || value === "fixture";
}

function assessmentContext() {
  return {
    id: state.selectedEvaluationId,
    roleVersion: state.roleVersion,
    version: state.assessmentVersion,
    signal: state.assessmentController.signal,
  };
}

function assessmentIsCurrent(context) {
  return context.roleVersion === state.roleVersion && context.version === state.assessmentVersion
    && context.id === state.selectedEvaluationId && !context.signal.aborted;
}

function assessmentPath(context, suffix = "") {
  return `/api/v1/evaluations/${encodeURIComponent(context.id)}${suffix}`;
}

function updateAssessmentControls() {
  const authenticated = state.authenticated && !state.switchingRole && !state.authenticationRequest;
  const ready = authenticated && Boolean(state.selectedEvaluation) && !state.assessmentLoading;
  const busy = Boolean(state.pendingAssessmentAction) || state.historiesLoading;
  const assessmentBusy = busy || state.assessmentLoading;
  const blueReady = ready && isTerminalAssessment(state.selectedEvaluation) && state.role === "blue" && !busy;
  $("blue-assessment").disabled = !authenticated || assessmentBusy || !state.sessionsLoaded || !state.evaluations.length;
  $("blue-instructions").disabled = !blueReady;
  $("analyze-findings").disabled = !blueReady;
  $("analyze-findings").textContent = state.pendingAssessmentAction === "analysis" ? "Analyzing..." : "Analyze recorded findings";
  $("blue-recipient").disabled = !ready || !canShareAssessment() || busy || !state.recipients.length;
  $("share-blue").disabled = $("blue-recipient").disabled || !state.recipients.some((item) => item.actor_id === $("blue-recipient").value);
  $("share-blue").textContent = state.pendingAssessmentAction === "share" ? "Sharing..." : "Share with Blue Team";
  $("refresh-blue-history").disabled = !ready || !canReadBlueHistory() || busy;
  $("refresh-blue-history").textContent = state.historiesLoading ? "Refreshing..." : "Refresh history";
  ["remediation-status", "remediation-notes", "remediation-evidence", "record-remediation"].forEach((id) => { $(id).disabled = !blueReady; });
  $("record-remediation").textContent = state.pendingAssessmentAction === "remediation" ? "Recording..." : "Record notes";
  const implemented = $("remediation-status").value === "implemented";
  $("remediation-evidence").required = implemented;
  $("remediation-evidence-label").textContent = implemented
    ? "Implementation evidence (required, up to 2000 characters)"
    : "Supporting evidence (optional, up to 2000 characters)";
  $("role").disabled = !authenticated;
  $("role").setAttribute("aria-disabled", String(!authenticated));
  $("create-evaluation").disabled = !authenticated || !roleProfiles[state.role].canCreate || state.creatingEvaluation;
  $("run-validation").disabled = !authenticated || !roleProfiles[state.role].canReview || state.validating;
  $("refresh").disabled = !authenticated || assessmentBusy || state.sessionsRefreshing;
  document.querySelectorAll(".session-link").forEach((button) => { button.disabled = !authenticated || assessmentBusy; });
}

function clearAssessment() {
  state.assessmentController?.abort();
  state.assessmentController = null;
  state.assessmentVersion += 1;
  state.selectedEvaluationId = "";
  state.selectedEvaluation = null;
  state.assessmentLoading = false;
  state.historiesLoading = false;
  state.historiesRequest = null;
  state.pendingAssessmentAction = "";
  state.recipients = [];
  ["blue-analysis-form", "blue-share-form", "remediation-form"].forEach((id) => $(id).reset());
  $("blue-assessment").value = "";
  $("blue-recipient").replaceChildren(textElement("option", "", "Select a Blue Team recipient"));
  $("blue-recipient").firstElementChild.value = "";
  ["assessment-message", "blue-analysis-message", "blue-share-message", "remediation-message"].forEach((id) => setMessage(id, ""));
  $("blue-share-form").hidden = true;
  $("blue-history").hidden = true;
  $("blue-history").setAttribute("aria-busy", "false");
  $("remediation-notes-panel").hidden = true;
  $("remediation-notes-panel").open = false;
  $("blue-analyses").replaceChildren();
  $("remediation-history").replaceChildren();
  renderEvaluationResult({});
  $("result-state").textContent = "waiting";
  $("result-response").textContent = "Select an authorized session to review its result.";
  $("result-prompt").textContent = "";
  updateAssessmentControls();
}

function renderAssessmentSelector(errorMessage = "") {
  const items = state.evaluations;
  const placeholder = !state.sessionsLoaded ? "Loading authorized assessments..."
    : items.length ? "Select an authorized assessment" : "No authorized assessments";
  const option = textElement("option", "", placeholder);
  option.value = "";
  $("blue-assessment").replaceChildren(option);
  items.forEach((item) => {
    const entry = textElement("option", "", `${String(item.session_id || item.id).slice(0, 12)} · ${item.state} · ${formatTime(item.created_at)}`);
    entry.value = item.id;
    $("blue-assessment").append(entry);
  });
  $("blue-assessment").value = state.selectedEvaluationId;
  $("blue-assessment-status").textContent = errorMessage || (!state.sessionsLoaded ? "Loading authorized assessments..."
    : !items.length ? "No authorized assessments yet. A Red Team owner or administrator must share an assessment with your Blue Team account."
      : state.selectedEvaluation ? "Stored evidence is loaded for the selected assessment. Instructions only supplement that evidence."
        : "Select an authorized assessment here or in Evaluation Sessions to load its recorded evidence and history.");
  updateAssessmentControls();
}

function appendRecordMetadata(card, entries) {
  const metadata = textElement("div", "context-list", "");
  entries.forEach(([label, value]) => {
    const row = textElement("div", "context-row", "");
    row.append(textElement("span", "", label), textElement("small", "", value || "—"));
    metadata.append(row);
  });
  card.append(metadata);
}

function renderBlueAnalyses(items) {
  const container = $("blue-analyses");
  container.replaceChildren();
  if (!items.length) {
    container.append(textElement("div", "empty", "No defensive analyses recorded for this assessment."));
    return;
  }
  items.forEach((item) => {
    const card = textElement("div", "result-output", "");
    card.append(textElement("span", "field-label", `Defensive output · advisory / unverified · ${item.state || "unknown"}`));
    appendRecordMetadata(card, [
      ["Analysis / source assessment", `${item.id} / ${item.source_evaluation_id}`],
      ["Actor", item.actor_id],
      ["Created / finished", `${formatTime(item.created_at)} / ${formatTime(item.finished_at)}`],
      ["Defensive model", typeof item.model === "string" ? item.model : item.model?.name || item.model?.model || "Not reported"],
      ["Source evidence type", item.source_evidence_type || item.source_model?.evidence_type || "Not reported"],
    ]);
    if (item.source_fixture || isFixtureType(item.source_evidence_type) || isFixtureEvidence(state.selectedEvaluation)) {
      card.append(textElement("div", "fixture-warning", "Source evidence: Test Fixture — Not Real Model Evidence"));
    }
    if (isFixtureType(item.model?.evidence_type) || item.model?.provider === "fixture") {
      card.append(textElement("div", "fixture-warning", "Defensive output: Test Fixture — Not Real Model Evidence"));
    }
    const error = typeof item.error === "string" ? item.error : item.error?.message;
    card.append(textElement("pre", "", item.response ?? (error ? `No defensive response. ${error}` : "No defensive response yet. Refresh history to check progress.")));
    if (error && item.response) card.append(textElement("p", "message error", error));
    card.append(textElement("p", "muted", "Recommended / advisory only · not implemented · not retested · not verified."));
    container.append(card);
  });
}

function renderRemediations(items) {
  const container = $("remediation-history");
  container.replaceChildren();
  if (!items.length) {
    container.append(textElement("div", "empty", "No remediation notes recorded for this assessment."));
    return;
  }
  items.forEach((item) => {
    const card = textElement("div", "result-output", "");
    card.append(textElement("span", "field-label", item.status === "implemented" ? "Implemented (user-reported) · unverified" : "Recommended · unverified"));
    appendRecordMetadata(card, [["Actor", item.actor_id], ["Recorded", formatTime(item.created_at)]]);
    card.append(textElement("span", "field-label", "Remediation notes"), textElement("pre", "", item.notes || "No notes supplied."));
    card.append(textElement("span", "field-label", "User-supplied evidence"), textElement("pre", "", item.evidence || "No supporting evidence recorded."));
    card.append(textElement("p", "muted", "Recorded separately from analysis · not retested · not verified."));
    container.append(card);
  });
}

async function loadBlueHistories(context) {
  if (!assessmentIsCurrent(context) || !canReadBlueHistory()) return false;
  if (state.historiesRequest) return state.historiesRequest.promise;
  const request = { promise: null };
  state.historiesRequest = request;
  state.historiesLoading = true;
  $("blue-analyses").replaceChildren(textElement("div", "empty", "Loading defensive analysis history..."));
  $("remediation-history").replaceChildren(textElement("div", "empty", "Loading remediation notes..."));
  $("blue-history").setAttribute("aria-busy", "true");
  updateAssessmentControls();
  request.promise = (async () => {
    try {
      const results = await Promise.allSettled([
        apiWithReauthentication(assessmentPath(context, "/blue-analyses"), { signal: context.signal }),
        apiWithReauthentication(assessmentPath(context, "/remediations"), { signal: context.signal }),
      ]);
      if (!assessmentIsCurrent(context)) return false;
      let loaded = true;
      results.forEach((result, index) => {
        const key = index === 0 ? "analyses" : "remediations";
        const id = index === 0 ? "blue-analyses" : "remediation-history";
        if (result.status === "fulfilled" && Array.isArray(result.value[key])) {
          if (index === 0) renderBlueAnalyses(result.value[key]);
          else renderRemediations(result.value[key]);
        } else {
          loaded = false;
          const message = result.status === "rejected" ? result.reason.message : "Invalid history response.";
          $(id).replaceChildren(textElement("div", "message error", `${message} Use Refresh history to try again.`));
        }
      });
      return loaded;
    } catch (error) {
      if (assessmentIsCurrent(context)) {
        ["blue-analyses", "remediation-history"].forEach((id) => {
          $(id).replaceChildren(textElement("div", "message error", `${error.message} Use Refresh history to try again.`));
        });
      }
      return false;
    } finally {
      if (assessmentIsCurrent(context) && state.historiesRequest === request) {
        state.historiesRequest = null;
        state.historiesLoading = false;
        $("blue-history").setAttribute("aria-busy", "false");
        updateAssessmentControls();
      }
    }
  })();
  return request.promise;
}

async function loadBlueRecipients(context) {
  if (!assessmentIsCurrent(context) || !canShareAssessment()) return;
  setMessage("blue-share-message", "Loading eligible Blue Team recipients...");
  try {
    const data = await apiWithReauthentication("/api/v1/blue-team/recipients", { signal: context.signal });
    if (!assessmentIsCurrent(context)) return;
    if (!Array.isArray(data.recipients)) throw new Error("Invalid recipient response.");
    state.recipients = data.recipients.filter((item) => typeof item.actor_id === "string" && item.actor_id);
    state.recipients.forEach((item) => {
      const option = textElement("option", "", item.actor_id);
      option.value = item.actor_id;
      $("blue-recipient").append(option);
    });
    setMessage("blue-share-message", state.recipients.length ? "Select the recipient to grant access explicitly." : "No eligible Blue Team recipients are available.");
  } catch (error) {
    if (assessmentIsCurrent(context)) setMessage("blue-share-message", `${error.message} Select this session again to retry.`, true);
  }
}

async function submitAssessmentAction(action, suffix, payload, messageId, onSaved) {
  if (!state.authenticated || state.switchingRole || !state.selectedEvaluation || state.assessmentLoading
    || state.pendingAssessmentAction || state.historiesLoading) return;
  const context = assessmentContext();
  state.pendingAssessmentAction = action;
  setMessage(messageId, action === "analysis" ? "Analyzing stored findings. Waiting for defensive output..." : "Saving...");
  updateAssessmentControls();
  try {
    const result = await apiWithReauthentication(assessmentPath(context, suffix), { method: "POST", body: JSON.stringify(payload), signal: context.signal });
    if (assessmentIsCurrent(context)) await onSaved(context, result);
  } catch (error) {
    if (assessmentIsCurrent(context)) setMessage(messageId, error.message, true);
  } finally {
    if (assessmentIsCurrent(context)) {
      state.pendingAssessmentAction = "";
      updateAssessmentControls();
    }
  }
}

function applyRole(roleKey, actorId = null) {
  const profile = roleProfiles[roleKey] || roleProfiles.admin;
  state.roleVersion += 1;
  state.sessionRequest?.controller.abort();
  state.sessionRequest = null;
  state.auditRequest = null;
  state.sessionsRefreshing = false;
  state.sessionsLoaded = false;
  state.evaluations = [];
  state.creatingEvaluation = false;
  state.validating = false;
  state.role = roleKey in roleProfiles ? roleKey : "admin";
  state.actorId = actorId;
  clearAssessment();
  document.body.dataset.role = state.role;
  particleField.setRole(state.role);
  $("role").value = state.role;
  $("role").setAttribute("aria-disabled", String(!state.authenticated || state.switchingRole));
  $("workspace-role").innerHTML = `${profile.name} <b>● ACTIVE</b>`;
  $("workspace-label").textContent = profile.workspace;
  $("workspace-eyebrow").textContent = profile.eyebrow;
  $("workspace-title").innerHTML = profile.title;
  $("workspace-copy").textContent = profile.copy;
  $("validation-eyebrow").textContent = profile.validationEyebrow;
  $("validation-title").textContent = profile.validationTitle;
  $("validation-copy").textContent = profile.validationCopy;
  $("evaluation-eyebrow").textContent = profile.evaluationEyebrow;
  $("evaluation-title").textContent = profile.evaluationTitle;
  $("evaluation-pill").textContent = profile.evaluationPill;
  $("prompt-label").textContent = profile.promptLabel;
  $("prompt").placeholder = profile.promptPlaceholder;
  $("prompt").disabled = !profile.canCreate;
  $("prompt").value = "";
  $("evaluation-form").hidden = !profile.canCreate;
  $("blue-analysis-form").hidden = state.role !== "blue";
  $("role-context").hidden = profile.canCreate;
  $("context-scope").textContent = "Checking authorized workspace scope...";
  $("workspace-policy").textContent = "Loading policy...";
  $("workspace-findings").textContent = "Loading authorized findings...";
  $("policy-title").textContent = state.role === "auditor" ? "Policy reference" : "Defensive rules";
  $("findings-title").textContent = state.role === "blue" ? "Security events / findings" : "Authorized findings";
  $("evaluation-hint").textContent = profile.evaluationHint;
  $("create-evaluation").textContent = profile.evaluationButton;
  $("create-evaluation").disabled = !profile.canCreate || !state.authenticated || state.switchingRole;
  $("run-validation").disabled = !profile.canReview || !state.authenticated || state.switchingRole;
  $("run-validation").textContent = profile.canReview ? "Run validation" : "Review role only";
  $("sessions-eyebrow").textContent = profile.sessionsEyebrow;
  $("sessions-title").textContent = profile.sessionsTitle;
  $("audit-eyebrow").textContent = profile.auditEyebrow;
  $("audit-title").textContent = profile.auditTitle;
  $("refresh").disabled = false;
  $("refresh").textContent = "Refresh";
  $("evaluations").innerHTML = '<div class="empty">Loading authorized sessions...</div>';
  setSessionRefreshStatus("");
  $("authorization-status").textContent = "Checking identity";
  $("evaluation-message").textContent = "";
  $("evaluation-message").className = "message";
  $("validation-results").innerHTML = "";
  $("validation-summary").className = "validation-summary empty";
  $("validation-summary").textContent = profile.canReview ? "No validation run in this workspace yet." : "Running validation requires Auditor or Security Administrator access. Policy rules are available in this workspace.";
  renderAssessmentSelector();
  setAuditPending(profile.canReview);
}

function renderEvaluations(items) {
  if (state.selectedEvaluationId && !items.some((item) => item.id === state.selectedEvaluationId)) clearAssessment();
  renderAssessmentSelector();
  if (!items.length) {
    $("evaluations").innerHTML = `<div class="empty">${state.role === "blue" ? "No authorized assessments yet. A Red Team owner or administrator must share an assessment with your Blue Team account." : "No authorized evaluation sessions yet."}</div>`;
    return;
  }
  const rows = items.map((item) => `<tr><td><button class="session-link" data-evaluation-id="${escapeHtml(item.id)}"><code>${escapeHtml((item.session_id || item.id).slice(0, 12))}</code></button></td><td>${escapeHtml(item.actor_id)}</td><td class="state ${item.state === "failed" || item.state === "blocked" ? "block" : ""}">${escapeHtml(item.state.toUpperCase())}</td><td>${escapeHtml(formatTime(item.created_at))}</td><td>${escapeHtml(formatTime(item.finished_at))}</td></tr>`).join("");
  $("evaluations").innerHTML = `<table><thead><tr><th>Session</th><th>Actor</th><th>State</th><th>Created</th><th>Finished</th></tr></thead><tbody>${rows}</tbody></table>`;
  document.querySelectorAll(".session-link").forEach((button) => button.addEventListener("click", () => loadEvaluation(button.dataset.evaluationId)));
  updateAssessmentControls();
}

function renderValidation(result) {
  $("validation-summary").className = `validation-summary ${result.passed ? "pass" : "fail"}`;
  const runtimeNote = result.runtime ? ` · ${result.runtime.scope}` : "";
  $("validation-summary").textContent = result.passed ? `All controls passed · evidence recorded${runtimeNote}` : "One or more controls require review";
  $("validation-results").innerHTML = result.controls.map((item) => `<div class="control-row"><span>${escapeHtml(item.name)}</span><small>${escapeHtml(item.actual)} · ${escapeHtml(item.scope || "unspecified")}</small><b class="${item.passed ? "pass" : "fail"}">${item.passed ? "PASS" : "FAIL"}</b></div>`).join("");
}

function renderEvaluationResult(evaluation) {
  const evidence = evaluation.evidence || {};
  const model = evaluation.model || {};
  const error = evaluation.error || {};
  const decision = evaluation.policy || {};
  const providerNames = { fixture: "Test Fixture", openai_compatible: "OpenAI-Compatible", ollama: "Ollama / Local Endpoint", unconfigured: "Not Configured" };
  const provider = providerNames[model.provider] || model.provider || "—";
  const isFixture = isFixtureEvidence(evaluation);
  $("result-state").textContent = String(evaluation.state || "unknown").toUpperCase();
  $("result-state").className = `pill ${evaluation.state === "completed" ? "allow" : evaluation.state === "failed" || evaluation.state === "blocked" ? "block" : ""}`;
  $("result-session").textContent = evaluation.session_id || "—";
  $("result-provider").textContent = provider;
  $("result-model").textContent = model.name || "—";
  $("result-status").textContent = String(evaluation.state || "unknown").toUpperCase();
  $("result-decision").textContent = decision.allowed === undefined ? "—" : `${decision.allowed ? "ALLOW" : "BLOCK"} · ${decision.control || "policy"}`;
  $("result-timestamp").textContent = formatTime(evaluation.finished_at || evaluation.created_at);
  $("result-latency").textContent = evaluation.latency_ms === null || evaluation.latency_ms === undefined ? "—" : `${evaluation.latency_ms} ms`;
  $("result-response").textContent = evidence.target_response ?? evaluation.response ?? (error.message ? `No model response. ${error.message}` : "No model response returned.");
  $("result-original-input").hidden = !state.selectedEvaluationId;
  $("result-prompt").textContent = evidence.prompt_available === true && typeof evidence.original_prompt === "string"
    ? evidence.original_prompt
    : "Original input is unavailable for this recorded assessment.";
  $("result-finding").textContent = evaluation.finding ? evaluation.finding.summary : (error.message || "None");
  $("result-warning").hidden = !isFixture;
  const events = evaluation.audit_events || [];
  $("result-audit").innerHTML = events.length ? events.map((event) => `<span class="audit-event">#${escapeHtml(event.id)} ${escapeHtml(event.event_type)}</span>`).join("") : "—";
}

function setSessionRefreshStatus(message, kind = "") {
  const element = $("session-refresh-status");
  element.textContent = message;
  element.className = `refresh-status ${kind}`;
}

async function refreshSessions({ latest = false } = {}) {
  if (state.sessionRequest) {
    const previous = state.sessionRequest;
    const result = await previous.promise;
    if (!latest || previous.version !== state.roleVersion) return result;
    return refreshSessions();
  }
  const version = state.roleVersion;
  const request = { version, controller: new AbortController(), promise: null };
  state.sessionRequest = request;
  state.sessionsRefreshing = true;
  const button = $("refresh");
  button.disabled = true;
  button.textContent = "Refreshing...";
  $("evaluations").setAttribute("aria-busy", "true");
  setSessionRefreshStatus("Fetching latest sessions...");
  const timer = setTimeout(() => request.controller.abort(), 10000);
  request.promise = (async () => {
    try {
      const data = await apiWithReauthentication("/api/v1/evaluations", { signal: request.controller.signal });
      if (version !== state.roleVersion) return false;
      if (!Array.isArray(data.evaluations)) throw new Error("Evaluation sessions response was invalid");
      state.evaluations = data.evaluations;
      state.sessionsLoaded = true;
      renderEvaluations(state.evaluations);
      setSessionRefreshStatus(`Updated ${new Date().toLocaleTimeString()}`, "success");
      return true;
    } catch (error) {
      if (version !== state.roleVersion) return false;
      const message = error.name === "AbortError" ? "Refresh timed out. Please try again." : error.message;
      setSessionRefreshStatus(message || "Unable to refresh sessions", "error");
      if (!state.sessionsLoaded) $("evaluations").innerHTML = `<div class="empty">Unable to load sessions. ${escapeHtml(message)}</div>`;
      renderAssessmentSelector(`Unable to refresh authorized assessments: ${message}. Use Refresh to try again.`);
      return false;
    } finally {
      clearTimeout(timer);
      if (state.sessionRequest === request) {
        state.sessionRequest = null;
        state.sessionsRefreshing = false;
        $("evaluations").setAttribute("aria-busy", "false");
        button.textContent = "Refresh";
        updateAssessmentControls();
      }
    }
  })();
  return request.promise;
}

function setAuditPending(canReview) {
  $("refresh-audit").disabled = !canReview;
  $("refresh-audit").textContent = "Verify now";
  $("audit-badge").textContent = canReview ? "checking" : "restricted";
  $("audit-badge").className = "pill";
  $("audit-status").textContent = canReview ? "Checking the signed audit chain with Bayora..." : "Verification requires Auditor or Security Administrator access.";
}

async function refreshAuditStatus() {
  const profile = roleProfiles[state.role];
  const version = state.roleVersion;
  if (!profile.canReview) {
    setAuditPending(false);
    return;
  }
  if (state.auditRequest) return state.auditRequest;
  setAuditPending(true);
  $("refresh-audit").disabled = true;
  $("refresh-audit").textContent = "Verifying...";
  const request = (async () => {
    try {
      const audit = await apiWithReauthentication("/api/v1/audit/verify");
      if (version !== state.roleVersion) return;
      if (typeof audit.valid !== "boolean") throw new Error("Invalid audit verification response");
      $("audit-status").textContent = audit.valid ? `${audit.message} · ${audit.record_count} records · ${new Date().toLocaleTimeString()}` : audit.message;
      $("audit-badge").textContent = audit.valid ? "verified" : "integrity issue";
      $("audit-badge").className = `pill ${audit.valid ? "allow" : "block"}`;
    } catch (error) {
      if (version !== state.roleVersion) return;
      $("audit-status").textContent = `Audit verification unavailable: ${error.message}`;
      $("audit-badge").textContent = "unavailable";
      $("audit-badge").className = "pill block";
    } finally {
      if (version === state.roleVersion) {
        state.auditRequest = null;
        $("refresh-audit").disabled = false;
        $("refresh-audit").textContent = "Verify now";
      }
    }
  })();
  state.auditRequest = request;
  return request;
}

async function refreshProviderStatus() {
  const version = state.roleVersion;
  try {
    const provider = await apiWithReauthentication("/api/v1/provider/status");
    if (version !== state.roleVersion) return;
    $("llm-provider").textContent = provider.provider.display_name;
    $("llm-status").textContent = provider.health.status.replaceAll("_", " ").toUpperCase();
    $("llm-model").textContent = provider.provider.model || "—";
    $("llm-health-message").textContent = provider.health.message || "—";
  } catch (error) {
    if (version !== state.roleVersion) return;
    $("llm-status").textContent = "UNAVAILABLE";
    $("llm-health-message").textContent = error.message;
  }
}

async function refreshServiceHealth() {
  try {
    const response = await fetch("/healthz", { cache: "no-store" });
    const health = await response.json();
    $("health-status").textContent = response.ok && health.status === "ok" ? "Service operational" : "Service unavailable";
  } catch (_error) {
    $("health-status").textContent = "Service unavailable";
  }
}

async function refreshWorkspaceContext() {
  const version = state.roleVersion;
  await Promise.allSettled([
    (async () => {
      try {
        const actor = await apiWithReauthentication("/api/v1/me");
        if (version !== state.roleVersion) return;
        if (actor.role !== state.role || actor.actor_id !== state.actorId) {
          applyRole(actor.role, actor.actor_id);
          refreshDashboard();
          return;
        }
        $("authorization-status").textContent = `AUTHORIZED · ${actor.role.toUpperCase()}`;
        $("context-scope").textContent = `Authorized as ${actor.actor_id}. ${["admin", "auditor"].includes(actor.role) ? "Review access across evaluation tenants." : actor.role === "blue" ? "Your tenant's assessments and assessments explicitly shared with your account are visible." : "Only your tenant's authorized sessions and findings are visible."}`;
      } catch (error) {
        if (version !== state.roleVersion) return;
        $("authorization-status").textContent = "Authorization unavailable";
        $("context-scope").textContent = error.message;
      }
    })(),
    (async () => {
      try {
        const { policy } = await apiWithReauthentication("/api/v1/policy");
        if (version !== state.roleVersion) return;
        $("workspace-policy").innerHTML = Object.entries(policy).map(([key, value]) => `<div class="context-row"><span>${escapeHtml(key.replaceAll("_", " "))}</span><small>${escapeHtml(value)}</small></div>`).join("");
      } catch (error) {
        if (version === state.roleVersion) $("workspace-policy").textContent = `Policy unavailable: ${error.message}`;
      }
    })(),
    (async () => {
      try {
        const { findings } = await apiWithReauthentication("/api/v1/findings");
        if (version !== state.roleVersion) return;
        $("workspace-findings").innerHTML = findings.length ? findings.slice(0, 5).map((item) => `<div class="context-row"><span>${escapeHtml(item.summary)}</span><small>${escapeHtml(item.control)} · ${escapeHtml(formatTime(item.created_at))}</small></div>`).join("") : '<span class="muted">No findings in your authorized scope.</span>';
      } catch (error) {
        if (version === state.roleVersion) $("workspace-findings").textContent = `Findings unavailable: ${error.message}`;
      }
    })(),
  ]);
}

async function refreshDashboard({ latestSessions = false } = {}) {
  await Promise.allSettled([refreshSessions({ latest: latestSessions }), refreshAuditStatus(), refreshProviderStatus(), refreshServiceHealth(), refreshWorkspaceContext()]);
}

async function loadEvaluation(evaluationId, { submittedEvaluation = null } = {}) {
  if (!state.authenticated || state.switchingRole) return;
  clearAssessment();
  if (!evaluationId) {
    renderAssessmentSelector();
    return;
  }
  state.selectedEvaluationId = evaluationId;
  state.assessmentController = new AbortController();
  state.assessmentLoading = true;
  const context = assessmentContext();
  renderAssessmentSelector();
  if (submittedEvaluation) {
    renderEvaluationResult(submittedEvaluation);
    $("result-original-input").hidden = true;
    $("result-prompt").textContent = "";
  } else {
    $("result-state").textContent = "loading";
    $("result-response").textContent = "Loading recorded assessment evidence...";
  }
  setMessage("assessment-message", "Loading authorized assessment...");
  $("blue-assessment-status").textContent = "Loading recorded assessment evidence and history...";
  let failure = "";
  try {
    const evaluation = await apiWithReauthentication(assessmentPath(context), { signal: context.signal });
    if (!assessmentIsCurrent(context)) return;
    if (evaluation.id && evaluation.id !== context.id) throw new Error("The assessment response did not match the selected assessment.");
    state.selectedEvaluation = evaluation;
    renderEvaluationResult(evaluation);
    $("blue-history").hidden = !canReadBlueHistory();
    $("remediation-notes-panel").hidden = state.role !== "blue";
    $("blue-share-form").hidden = !canShareAssessment();
    setMessage("assessment-message", "");
    await Promise.all([loadBlueHistories(context), loadBlueRecipients(context)]);
  } catch (error) {
    if (!assessmentIsCurrent(context)) return;
    failure = `${error.message} Select this session again in the table to retry.`;
    if (!submittedEvaluation) {
      $("result-state").textContent = "unavailable";
      $("result-response").textContent = "Recorded assessment evidence could not be loaded.";
    }
    setMessage("assessment-message", failure, true);
  } finally {
    if (assessmentIsCurrent(context)) {
      state.assessmentLoading = false;
      renderAssessmentSelector(failure);
    }
  }
}

async function authenticate(usernameHint = "security-admin") {
  try {
    const actor = await api("/api/v1/me");
    state.authenticated = true;
    return actor;
  } catch (error) {
    if (error.status !== 401) throw error;
  }

  const username = window.prompt("Bayora username", usernameHint);
  if (!username) throw new Error("Authentication required.");
  const password = window.prompt("Bayora password");
  if (!password) throw new Error("Authentication required.");
  await api("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  const actor = await api("/api/v1/me");
  state.authenticated = true;
  return actor;
}

async function apiWithReauthentication(path, options = {}) {
  const version = state.roleVersion;
  try {
    return await api(path, options);
  } catch (error) {
    if (error.status !== 401) throw error;
    if (version !== state.roleVersion || state.switchingRole || options.signal?.aborted) throw error;
    if (!state.authenticationRequest) {
      state.authenticated = false;
      state.authenticationRequest = authenticate(roleUsernames[state.role] || "security-admin");
      updateAssessmentControls();
    }
    const request = state.authenticationRequest;
    let actor;
    try {
      actor = await request;
    } catch (authenticationError) {
      if (version === state.roleVersion) {
        state.authenticated = false;
        applyRole(state.role);
        $("authorization-status").textContent = "Authentication required";
        setMessage("evaluation-message", authenticationError.message, true);
      }
      throw authenticationError;
    } finally {
      if (state.authenticationRequest === request) {
        state.authenticationRequest = null;
        updateAssessmentControls();
      }
    }
    if (version !== state.roleVersion || options.signal?.aborted) throw new DOMException("Workspace changed.", "AbortError");
    if (actor.role !== state.role || actor.actor_id !== state.actorId) {
      applyRole(actor.role, actor.actor_id);
      refreshDashboard();
      throw new DOMException("Account changed. Select an assessment in the refreshed workspace.", "AbortError");
    }
    return api(path, options);
  }
}

async function switchAuthenticatedRole(requestedRole) {
  if (!state.authenticated || state.authenticationRequest || state.switchingRole || requestedRole === state.role) {
    $("role").value = state.role;
    return;
  }
  const previousRole = state.role;
  state.switchingRole = true;
  $("role").disabled = true;
  $("create-evaluation").disabled = true;
  $("run-validation").disabled = true;
  updateAssessmentControls();
  let loginStarted = false;
  try {
    const username = window.prompt("Bayora username", roleUsernames[requestedRole] || "");
    if (!username) throw new Error("Role switch cancelled.");
    const password = window.prompt("Bayora password");
    if (!password) throw new Error("Role switch cancelled.");
    loginStarted = true;
    state.authenticated = false;
    applyRole(previousRole);
    await api("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    const actor = await api("/api/v1/me");
    state.authenticated = true;
    applyRole(actor.role, actor.actor_id);
  } catch (error) {
    if (loginStarted) {
      try {
        const actor = await api("/api/v1/me");
        state.authenticated = true;
        applyRole(actor.role, actor.actor_id);
      } catch (_identityError) {
        state.authenticated = false;
        applyRole(previousRole);
        $("authorization-status").textContent = "Authentication required";
      }
    }
    $("role").value = state.role;
    setMessage("evaluation-message", error.message, true);
  } finally {
    state.switchingRole = false;
    $("role").disabled = !state.authenticated;
    $("role").setAttribute("aria-disabled", String(!state.authenticated));
    $("create-evaluation").disabled = !state.authenticated || !roleProfiles[state.role].canCreate || state.creatingEvaluation;
    $("run-validation").disabled = !state.authenticated || !roleProfiles[state.role].canReview || state.validating;
    updateAssessmentControls();
    if (state.authenticated) await refreshDashboard();
  }
}

$("role").addEventListener("change", () => {
  switchAuthenticatedRole($("role").value);
});

$("refresh").addEventListener("click", () => refreshSessions());
$("refresh-audit").addEventListener("click", refreshAuditStatus);

$("blue-assessment").addEventListener("change", () => loadEvaluation($("blue-assessment").value));
$("blue-recipient").addEventListener("change", updateAssessmentControls);
$("remediation-status").addEventListener("change", updateAssessmentControls);
$("refresh-blue-history").addEventListener("click", () => {
  if (!$("refresh-blue-history").disabled) loadBlueHistories(assessmentContext());
});

$("blue-analysis-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.role !== "blue" || $("analyze-findings").disabled) return;
  const instructions = $("blue-instructions").value.trim();
  if (instructions.length > 2000) {
    setMessage("blue-analysis-message", "Instructions must be at most 2000 characters.", true);
    return;
  }
  await submitAssessmentAction("analysis", "/blue-analyses", instructions ? { instructions } : {}, "blue-analysis-message", async (context, result) => {
    if (result.state === "completed") $("blue-instructions").value = "";
    const loaded = await loadBlueHistories(context);
    if (!assessmentIsCurrent(context)) return;
    if (result.state === "failed") {
      setMessage("blue-analysis-message", `Analysis failed: ${result.error?.message || "defensive model output unavailable"}. Failure recorded in history; no fix or retest was performed.`, true);
    } else if (result.state === "completed") {
      setMessage("blue-analysis-message", loaded
        ? "Analysis output recorded. It remains advisory and unverified; no fix or retest was performed."
        : "Analysis output recorded, but history could not be refreshed. Use Refresh history to read it back.");
    } else {
      setMessage("blue-analysis-message", "Analysis is pending. Use Refresh history to check its recorded state.");
    }
  });
});

$("blue-share-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!canShareAssessment() || $("share-blue").disabled) return;
  const recipient = $("blue-recipient").value;
  await submitAssessmentAction("share", "/blue-team-access", { blue_actor_id: recipient }, "blue-share-message", async (context) => {
    if (!assessmentIsCurrent(context)) return;
    $("blue-recipient").value = "";
    setMessage("blue-share-message", `${recipient} now has permission to this assessment. No data was automatically transferred and no analysis was started.`);
  });
});

$("remediation-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.role !== "blue" || $("record-remediation").disabled) return;
  const status = $("remediation-status").value;
  const notes = $("remediation-notes").value.trim();
  const evidence = $("remediation-evidence").value.trim();
  if (!notes) {
    setMessage("remediation-message", "Enter remediation notes before recording them.", true);
    return;
  }
  if (!["recommended", "implemented"].includes(status) || notes.length > 2000 || evidence.length > 2000) {
    setMessage("remediation-message", "Choose a supported status and keep notes and evidence to at most 2000 characters each.", true);
    return;
  }
  if (status === "implemented" && !evidence) {
    setMessage("remediation-message", "Implementation evidence is required for an implemented (user-reported) note.", true);
    return;
  }
  await submitAssessmentAction("remediation", "/remediations", { status, notes, ...(evidence ? { evidence } : {}) }, "remediation-message", async (context) => {
    $("remediation-form").reset();
    const loaded = await loadBlueHistories(context);
    if (assessmentIsCurrent(context)) setMessage("remediation-message", loaded
      ? "Notes recorded separately. Implementation is user-reported; no retest or verification has been performed."
      : "Notes saved, but history could not be refreshed. Use Refresh history to read them back.");
  });
});

$("run-validation").addEventListener("click", async () => {
  if (!state.authenticated || state.switchingRole || state.validating || !roleProfiles[state.role].canReview) return;
  state.validating = true;
  const version = state.roleVersion;
  const button = $("run-validation");
  button.disabled = true;
  button.textContent = "Running...";
  try {
    const validation = await apiWithReauthentication("/api/v1/security/validation", { method: "POST", body: "{}" });
    if (version === state.roleVersion) renderValidation(validation);
  } catch (error) {
    if (version !== state.roleVersion) return;
    $("validation-summary").className = "validation-summary fail";
    $("validation-summary").textContent = error.message;
  } finally {
    if (version === state.roleVersion) {
      state.validating = false;
      button.disabled = !state.authenticated || state.switchingRole || !roleProfiles[state.role].canReview;
      button.textContent = roleProfiles[state.role].canReview ? "Run validation" : "Review role only";
      refreshDashboard();
    }
  }
});

$("create-evaluation").addEventListener("click", async () => {
  if (!state.authenticated || state.switchingRole || state.creatingEvaluation) return;
  const message = $("evaluation-message");
  message.className = "message";
  if (!roleProfiles[state.role].canCreate) {
    message.className = "message error";
    message.textContent = "Evaluation creation requires Red Team authorization.";
    return;
  }
  const version = state.roleVersion;
  const selectionVersion = state.assessmentVersion;
  const button = $("create-evaluation");
  try {
    const prompt = $("prompt").value;
    if (!prompt.trim()) throw new Error("Enter an evaluation prompt");
    state.creatingEvaluation = true;
    button.disabled = true;
    button.textContent = "Evaluating...";
    message.textContent = "Evaluation submitted. Waiting for the provider response...";
    const evaluation = await apiWithReauthentication("/api/v1/evaluations", { method: "POST", body: JSON.stringify({ prompt }) });
    if (version !== state.roleVersion) return;
    const selectSubmitted = selectionVersion === state.assessmentVersion;
    if (selectSubmitted) {
      clearAssessment();
      renderEvaluationResult(evaluation);
    }
    const submissionSelectionVersion = state.assessmentVersion;
    if (evaluation.state === "completed") message.textContent = `Session ${evaluation.session_id.slice(0, 12)} completed after model response received.`;
    else if (evaluation.state === "failed") { message.className = "message error"; message.textContent = `Evaluation failed: ${evaluation.error?.message || "model backend unavailable"}`; }
    else message.textContent = `Session ${evaluation.session_id.slice(0, 12)} ended with state ${evaluation.state}.`;
    $("prompt").value = "";
    await refreshDashboard({ latestSessions: true });
    if (version === state.roleVersion && selectSubmitted && submissionSelectionVersion === state.assessmentVersion) {
      loadEvaluation(evaluation.id, { submittedEvaluation: evaluation });
    }
  } catch (error) {
    if (version !== state.roleVersion) return;
    message.className = "message error";
    message.textContent = error.message;
  } finally {
    if (version === state.roleVersion) {
      state.creatingEvaluation = false;
      button.disabled = !state.authenticated || state.switchingRole || !roleProfiles[state.role].canCreate;
      button.textContent = roleProfiles[state.role].evaluationButton;
    }
  }
});

async function startApplication() {
  try {
    const actor = await authenticate();
    if (!roleProfiles[actor.role]) throw new Error("Authenticated role is not supported by this client.");
    applyRole(actor.role, actor.actor_id);
    $("role").setAttribute("aria-disabled", "false");
    refreshDashboard();
  } catch (error) {
    $("authorization-status").textContent = "Authentication required";
    $("context-scope").textContent = error.message;
  }
}

startApplication();
