
import os
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
from collections import Counter
import re
import io
import json

# Optional imports for resume parsing
try:
    import PyPDF2
except Exception:
    PyPDF2 = None

try:
    import docx
except Exception:
    docx = None

# Optional OpenAI for AI interviewing
try:
    from openai import OpenAI  # SDK v1+
except Exception:
    OpenAI = None

app = Flask(__name__)

# ----------------------------
# Utilities
# ----------------------------
SOFT_SKILL_KEYWORDS = {
    "communication": ["communicat", "present", "verbal", "written", "storytell"],
    "teamwork": ["team", "collaborat", "cross-functional", "stakeholder"],
    "leadership": ["lead", "mentor", "coach", "manage", "ownership"],
    "problem_solving": ["problem", "solve", "optimiz", "debug", "root cause"],
    "adaptability": ["adapt", "learn", "fast", "agile", "flexible"],
    "time_management": ["deadline", "priorit", "time", "schedule"]
}

FILLER_WORDS = set(["um", "uh", "like", "you know", "sort of", "kinda", "actually", "basically", "literally"])

STAR_HINTS = ["situation", "task", "action", "result"]

INTERVIEW_QUESTION_BANK = {
    "general": [
        "Tell me about yourself.",
        "What are your strengths and weaknesses?",
        "Describe a challenging situation you faced and how you handled it.",
        "Why should we hire you?",
        "Where do you see yourself in five years?"
    ],
    "software_engineer": [
        "Walk me through a project where you used data structures or algorithms to improve performance.",
        "How do you approach debugging a complex issue in production?",
        "Explain a time you collaborated with cross-functional teams to deliver a feature.",
        "Describe your experience with version control and code reviews.",
        "What steps do you take to ensure code quality and reliability?"
    ],
    "aiml": [
        "Tell me about an ML project you built end-to-end. How did you frame the problem and evaluate success?",
        "How do you prevent overfitting? Give practical techniques.",
        "Explain a time you handled imbalanced data.",
        "How would you design a real-time inference pipeline for an ML model?",
        "What trade-offs do you consider when selecting a model for production?"
    ],
    "hr": [
        "What motivates you at work?",
        "Tell me about a time you dealt with a conflict in a team.",
        "Describe a failure and what you learned from it.",
        "How do you handle feedback and criticism?",
        "What kind of work environment helps you perform best?"
    ]
}

def clean_text(t):
    return re.sub(r'\s+', ' ', (t or "")).strip()

def extract_text_from_pdf(file_stream):
    if PyPDF2 is None:
        return ""
    try:
        reader = PyPDF2.PdfReader(file_stream)
        out = []
        for page in reader.pages:
            out.append(page.extract_text() or "")
        return "\n".join(out)
    except Exception:
        return ""

def extract_text_from_docx(file_stream):
    if docx is None:
        return ""
    try:
        # docx.Document needs a path or file-like
        file_stream.seek(0)
        doc = docx.Document(file_stream)
        return "\n".join([p.text for p in doc.paragraphs])
    except Exception:
        return ""

def naive_resume_text(file_storage):
    filename = secure_filename(file_storage.filename)
    ext = os.path.splitext(filename)[1].lower()
    data = file_storage.read()
    bio = io.BytesIO(data)

    if ext == ".pdf":
        txt = extract_text_from_pdf(bio)
    elif ext in (".docx",):
        txt = extract_text_from_docx(bio)
    else:
        try:
            txt = data.decode("utf-8", errors="ignore")
        except Exception:
            txt = ""

    return clean_text(txt)

def keywordize(text):
    # simple tokenizer
    words = re.findall(r"[a-zA-Z][a-zA-Z\-]+", (text or "").lower())
    return Counter(words)

def compute_ats_score(resume_text, job_desc):
    r_words = keywordize(resume_text)
    j_words = keywordize(job_desc)

    # Identify important keywords from job description (top unique nouns-ish approximated by frequency)
    # For simplicity, pick top 30 non-stop words by frequency excluding very common words
    stop = set("""a an the and or of to in for with on at by from is are were was be been being as it this that these those i you we they he she them us our your their""".split())
    # take job words minus stop
    job_terms = [w for w, c in j_words.most_common(300) if w not in stop and len(w) > 2]
    job_terms = job_terms[:30]

    # overlap
    present = [w for w in job_terms if r_words[w] > 0]
    missing = [w for w in job_terms if r_words[w] == 0]

    # simple scoring: 60% from keyword overlap, 20% from length & sections, 20% from formatting hints
    if len(job_terms) == 0:
        kw_score = 50
    else:
        kw_score = int(60 * (len(present) / max(1, len(job_terms))))

    # heuristics
    length_score = 0
    length = len(resume_text.split())
    if 250 <= length <= 900:
        length_score = 20
    elif 150 <= length < 250 or 900 < length <= 1500:
        length_score = 12
    else:
        length_score = 6

    # formatting hints: check for sections
    sections = ["education", "experience", "projects", "skills", "certifications", "achievements"]
    fmt_hits = sum(1 for s in sections if s in resume_text.lower())
    fmt_score = int(min(20, (fmt_hits / len(sections)) * 20))

    score = kw_score + length_score + fmt_score
    return max(0, min(100, score)), present, missing

def soft_skill_feedback(answer_text):
    text = (answer_text or "").strip()
    words = re.findall(r"[a-zA-Z']+", text.lower())
    word_count = len(words)

    filler_hits = [w for w in FILLER_WORDS if w in text.lower()]
    star_coverage = sum(1 for h in STAR_HINTS if h in text.lower())

    # sentence count
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    avg_len = (sum(len(s.split()) for s in sentences) / len(sentences)) if sentences else 0

    feedback = []
    # Length guidance
    if word_count < 60:
        feedback.append("Your answer is quite short. Aim for 90–150 words to add context and impact.")
    elif word_count > 220:
        feedback.append("Your answer is long. Try 120–180 words and trim tangents.")
    else:
        feedback.append("Good length.")

    # Filler check
    if filler_hits:
        feedback.append(f"Reduce filler words ({', '.join(filler_hits)}). Pause briefly instead.")

    # STAR method
    if star_coverage <= 1:
        feedback.append("Use the STAR method: briefly outline Situation, Task, Action, Result.")
    else:
        feedback.append("Nice use of the STAR structure—ensure the Result is quantified.")

    # Quantification check
    if re.search(r"\b(\d+%?|\$\d+|[0-9]+k)\b", text) is None:
        feedback.append("Add numbers to demonstrate impact (e.g., 'reduced time by 20%').")

    # Clarity check via average sentence length
    if avg_len > 28:
        feedback.append("Shorten long sentences for clarity (aim for 15–22 words each).")

    # Soft skill coverage
    found = []
    for skill, keys in SOFT_SKILL_KEYWORDS.items():
        if any(k in text.lower() for k in keys):
            found.append(skill.replace("_", " "))
    if found:
        feedback.append("Strengths noted: " + ", ".join(found) + ".")

    # Overall summary
    summary = " ".join(feedback)
    return summary

def next_question(mode="general", role_hint="general", asked_idx=0):
    bank = INTERVIEW_QUESTION_BANK.get(role_hint, []) or INTERVIEW_QUESTION_BANK.get(mode, []) or INTERVIEW_QUESTION_BANK["general"]
    idx = asked_idx % len(bank)
    return bank[idx]


def ai_enabled() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY")) and OpenAI is not None


def generate_ai_interview(role: str, company: str, difficulty: str, asked_idx: int, user_answer: str):
    """Use OpenAI to generate concise feedback and the next question.

    Returns: (feedback: str, next_question: str)
    """
    if not ai_enabled():
        return None, None

    client = OpenAI()

    sys_prompt = (
        "You are a senior interviewer conducting a mock interview for {company} "
        "({role}). Keep it realistic and job-ready. Ask one question at a time."
        " Provide concise, actionable feedback. Maintain a professional tone."
    ).format(company=company or "a top tech company", role=role or "Generalist")

    # Force JSON output for reliability
    instructions = {
        "asked_index": int(asked_idx),
        "company": company or "",
        "role": role or "",
        "difficulty": (difficulty or "Medium").title(),
        "user_answer": user_answer or "",
        "requirements": {
            "feedback_style": "bullet points, at most 6 bullets; include STAR and quantification guidance",
            "next_question": "role and company specific, realistic, difficulty-appropriate",
            "length": "feedback <= 120 words",
        }
    }

    user_prompt = (
        "You will return strict JSON with keys 'feedback' and 'question'. "
        "If there is no user answer yet, set 'feedback' to an empty string and only provide the first 'question'. "
        "Context:\n" + json.dumps(instructions, ensure_ascii=False)
    )

    try:
        resp = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.5,
        )
        content = resp.choices[0].message.content.strip()
        # Attempt to parse JSON from content
        data = {}
        try:
            data = json.loads(content)
        except Exception:
            # Fallback: try to extract JSON substring
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1 and end > start:
                data = json.loads(content[start:end+1])
        feedback = clean_text(data.get("feedback", ""))
        question = clean_text(data.get("question", ""))
        return feedback, question
    except Exception:
        return None, None

# ----------------------------
# Routes
# ----------------------------

@app.route("/")
def home():
    return render_template("index.html", ai_enabled=ai_enabled())

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    mode = data.get("mode", "general")  # 'interview' or 'softskills' or 'general'
    message = data.get("message", "")
    role = data.get("role", "general")
    asked_idx = int(data.get("asked_idx", 0))
    company = data.get("company", "")
    difficulty = data.get("difficulty", "Medium")

    if mode == "interview":
        # If AI available, use it; otherwise local heuristics
        if ai_enabled():
            fb, q = generate_ai_interview(role=role, company=company, difficulty=difficulty, asked_idx=asked_idx, user_answer=message)
            if not q:
                # fall back if AI failed
                feedback = soft_skill_feedback(message)
                question = next_question("hr", role_hint=role, asked_idx=asked_idx + 1)
                return jsonify({
                    "reply": f"Feedback: {feedback}",
                    "next_question": question,
                    "asked_idx": asked_idx + 1
                })
            return jsonify({
                "reply": (fb or ""),
                "next_question": q,
                "asked_idx": asked_idx + 1
            })
        else:
            feedback = soft_skill_feedback(message)
            question = next_question("hr", role_hint=role, asked_idx=asked_idx + 1)
            return jsonify({
                "reply": f"Feedback: {feedback}",
                "next_question": question,
                "asked_idx": asked_idx + 1
            })

    elif mode == "softskills":
        fb = soft_skill_feedback(message)
        tips = ("Tip: Practice in front of a camera, slow down your pace, and emphasize key results. "
                "Structure answers with STAR and quantify impact.")
        return jsonify({"reply": fb + " " + tips})

    else:
        # general Q&A placeholder (local heuristic)
        return jsonify({"reply": "I'm your career prep assistant. Choose Interview Practice or upload a resume to get an ATS score."})

@app.route("/upload_resume", methods=["POST"])
def upload_resume():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["file"]
    text = naive_resume_text(f)
    if not text:
        return jsonify({"error": "Could not read file. Use PDF, DOCX, or TXT."}), 400
    return jsonify({"text": text[:20000]})

@app.route("/ats_score", methods=["POST"])
def ats_score():
    data = request.get_json(force=True)
    resume_text = data.get("resume_text", "")
    job_desc = data.get("job_desc", "")
    score, present, missing = compute_ats_score(resume_text, job_desc)
    return jsonify({
        "score": score,
        "present_keywords": present,
        "missing_keywords": missing
    })

# Health
@app.route("/health")
def health():
    return "ok", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
