
// Tabs
const tabs = document.querySelectorAll(".tab");
const panels = document.querySelectorAll(".tab-panel");
tabs.forEach(btn => {
  btn.addEventListener("click", () => {
    tabs.forEach(b => b.classList.remove("active"));
    panels.forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(btn.dataset.tab).classList.add("active");
  });
});

// Chat UI
const chatWindow = document.getElementById("chatWindow");
const userInput = document.getElementById("userInput");
const sendBtn = document.getElementById("sendBtn");
const startInterviewBtn = document.getElementById("startInterview");
const roleSelect = document.getElementById("role");
const companyInput = document.getElementById("company");
const difficultySelect = document.getElementById("difficulty");
let askedIdx = 0;
let currentMode = "interview";

// Voice elements
const micBtn = document.getElementById("micBtn");
const ttsToggle = document.getElementById("ttsToggle");
const autoSendToggle = document.getElementById("autoSendToggle");
const voiceStatus = document.getElementById("voiceStatus");
let recognition;
let isListening = false;
let interimTranscript = "";

// Header AI badge
const aiBadge = document.getElementById("aiBadge");
if(aiBadge){
  const enabled = ((window.__AI_ENABLED__ || "false") + "").toLowerCase() === "true";
  aiBadge.textContent = enabled ? "AI: On (OpenAI)" : "AI: Off (Local Mode)";
  aiBadge.style.color = enabled ? "#8ef5b5" : "#ffd27a";
}

function addMsg(text, who="bot"){
  const div = document.createElement("div");
  div.className = "msg " + (who === "user" ? "user" : "bot");
  div.textContent = text;
  chatWindow.appendChild(div);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

startInterviewBtn.addEventListener("click", async () => {
  askedIdx = 0;
  currentMode = "interview";
  chatWindow.innerHTML = "";
  addMsg("Starting mock interview. Answer the questions in 120–180 words using STAR (Situation, Task, Action, Result).");
  // ask first question
  const r = await fetch("/chat", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      mode: "interview",
      message: "",
      role: roleSelect.value,
      company: (companyInput?.value || "").trim(),
      difficulty: difficultySelect?.value || "Medium",
      asked_idx: askedIdx
    })
  });
  const data = await r.json();
  // Server returns feedback for previous (empty) and next question; ignore feedback initially
  addMsg(data.next_question, "bot");
  askedIdx = data.asked_idx;
});

sendBtn.addEventListener("click", async () => {
  const text = userInput.value.trim();
  if(!text) return;
  addMsg(text, "user");
  userInput.value = "";

  const r = await fetch("/chat", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      mode: currentMode,
      message: text,
      role: roleSelect.value,
      company: (companyInput?.value || "").trim(),
      difficulty: difficultySelect?.value || "Medium",
      asked_idx: askedIdx
    })
  });
  const data = await r.json();
  if(data.reply) addMsg(data.reply, "bot");
  if(data.next_question){
    addMsg(data.next_question, "bot");
  }
  if(typeof data.asked_idx === "number"){
    askedIdx = data.asked_idx;
  }

  // Speak the bot's reply/question if enabled
  if(ttsToggle?.checked){
    const toSpeak = [data.reply, data.next_question].filter(Boolean).join(". ");
    if(toSpeak){
      try { speakText(toSpeak); } catch (e) { /* noop */ }
    }
  }
});

// Resume & ATS
const resumeFile = document.getElementById("resumeFile");
const extractBtn = document.getElementById("extractBtn");
const resumeText = document.getElementById("resumeText");
const jobDesc = document.getElementById("jobDesc");
const scoreBtn = document.getElementById("scoreBtn");
const scoreCard = document.getElementById("scoreCard");
const scoreVal = document.getElementById("scoreVal");
const presentList = document.getElementById("presentList");
const missingList = document.getElementById("missingList");

extractBtn.addEventListener("click", async () => {
  if(!resumeFile.files[0]){
    alert("Select a resume file first.");
    return;
  }
  const fd = new FormData();
  fd.append("file", resumeFile.files[0]);
  const r = await fetch("/upload_resume", { method: "POST", body: fd });
  const data = await r.json();
  if(data.error){ alert(data.error); return; }
  resumeText.value = data.text;
});

scoreBtn.addEventListener("click", async () => {
  const r = await fetch("/ats_score", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ resume_text: resumeText.value, job_desc: jobDesc.value })
  });
  const data = await r.json();
  scoreVal.textContent = data.score;
  presentList.innerHTML = "";
  missingList.innerHTML = "";

  (data.present_keywords || []).forEach(k => {
    const li = document.createElement("li"); li.textContent = k; presentList.appendChild(li);
  });
  (data.missing_keywords || []).forEach(k => {
    const li = document.createElement("li"); li.textContent = k; missingList.appendChild(li);
  });

  scoreCard.classList.remove("hidden");
});

// ----------------------------
// Voice: Speech Recognition + TTS
// ----------------------------

function getRecognition(){
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if(!SR) return null;
  if(recognition) return recognition;
  recognition = new SR();
  recognition.lang = navigator.language || "en-US";
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;

  recognition.onstart = () => { isListening = true; setVoiceStatus("Listening..."); micBtn?.classList.add("active"); };
  recognition.onend = () => { isListening = false; setVoiceStatus(""); micBtn?.classList.remove("active"); };
  recognition.onerror = (e) => { setVoiceStatus("Mic error: " + (e.error || "unknown")); };
  recognition.onresult = (event) => {
    let finalTranscript = "";
    interimTranscript = "";
    for(let i=event.resultIndex; i<event.results.length; i++){
      const res = event.results[i];
      if(res.isFinal){ finalTranscript += res[0].transcript; }
      else { interimTranscript += res[0].transcript; }
    }
    const combined = (finalTranscript || interimTranscript).trim();
    if(combined){ userInput.value = combined; }
    if(finalTranscript && autoSendToggle?.checked){
      sendBtn.click();
    }
  };
  return recognition;
}

function setVoiceStatus(text){ if(voiceStatus){ voiceStatus.textContent = text; } }

function toggleListening(){
  const rec = getRecognition();
  if(!rec){
    alert("Speech Recognition not supported in this browser. Try Chrome on desktop.");
    return;
  }
  if(isListening){ rec.stop(); }
  else { rec.start(); }
}

function speakText(text){
  if(!("speechSynthesis" in window)) return;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = navigator.language || "en-US";
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(u);
}

micBtn?.addEventListener("click", toggleListening);
