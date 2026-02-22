"""TalentCopilot Streamlit frontend: chat, HITL confirmations, CV upload, job status."""
import os
import requests
import streamlit as st
from uuid import uuid4

# Backend URL - override with env
API_BASE = os.environ.get("TALENTCOPILOT_API_URL", "http://localhost:8000")


def headers():
    tid = st.session_state.get("tenant_id") or ""
    uid = st.session_state.get("user_id") or ""
    sid = st.session_state.get("session_id") or ""
    return {
        "X-Tenant-ID": str(tid),
        "X-User-ID": str(uid),
        "X-Session-ID": str(sid),
        "Content-Type": "application/json",
    }


def init_session():
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid4())
    if "tenant_id" not in st.session_state:
        st.session_state.tenant_id = str(uuid4())
    if "user_id" not in st.session_state:
        st.session_state.user_id = str(uuid4())
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "pending_confirmation" not in st.session_state:
        st.session_state.pending_confirmation = None
    if "job_ids" not in st.session_state:
        st.session_state.job_ids = []


def post_chat(message: str):
    r = requests.post(
        f"{API_BASE}/chat",
        json={
            "message": message,
            "tenant_id": st.session_state.tenant_id,
            "user_id": st.session_state.user_id,
            "session_id": st.session_state.session_id,
        },
        headers={"Content-Type": "application/json"},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def post_confirm(confirmation_id: str, approved: bool):
    r = requests.post(
        f"{API_BASE}/confirm",
        json={
            "confirmation_id": confirmation_id,
            "approved": approved,
            "tenant_id": st.session_state.tenant_id,
            "user_id": st.session_state.user_id,
            "session_id": st.session_state.session_id,
        },
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def upload_cv(file_bytes, filename: str):
    h = headers()
    del h["Content-Type"]
    r = requests.post(
        f"{API_BASE}/upload/cv",
        files={"file": (filename, file_bytes)},
        headers={k: v for k, v in h.items()},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def get_job(job_id: str):
    r = requests.get(
        f"{API_BASE}/jobs/{job_id}",
        headers=headers(),
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def get_workspace():
    r = requests.get(
        f"{API_BASE}/workspace",
        headers=headers(),
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def main():
    st.set_page_config(page_title="TalentCopilot", page_icon="🤖", layout="wide")
    init_session()

    st.sidebar.title("TalentCopilot")
    st.sidebar.caption("Recruiting assistant with HITL")
    st.sidebar.markdown("---")
    st.sidebar.subheader("Tenant / Session")
    st.sidebar.text_input("Tenant ID", value=st.session_state.tenant_id, key="tenant_id", disabled=False)
    st.sidebar.text_input("User ID", value=st.session_state.user_id, key="user_id", disabled=False)
    st.sidebar.text_input("Session ID", value=st.session_state.session_id, key="session_id", disabled=False)
    if st.sidebar.button("New session"):
        st.session_state.session_id = str(uuid4())
        st.session_state.messages = []
        st.session_state.pending_confirmation = None
        st.rerun()

    # Pending HITL confirmation
    if st.session_state.pending_confirmation:
        pc = st.session_state.pending_confirmation
        st.warning("**Confirmation required**")
        st.markdown(pc.get("prompt", ""))
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Yes", key="confirm_yes"):
                try:
                    resp = post_confirm(pc["confirmation_id"], True)
                    st.session_state.pending_confirmation = None
                    if resp.get("next_action") == "ingest_started" and resp.get("job_id"):
                        st.session_state.job_ids.append(str(resp["job_id"]))
                    st.success(resp.get("message", "Done."))
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
        with col2:
            if st.button("No", key="confirm_no"):
                try:
                    post_confirm(pc["confirmation_id"], False)
                    st.session_state.pending_confirmation = None
                    st.info("Action cancelled.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
        st.markdown("---")

    # CV Upload
    st.sidebar.subheader("Upload CV")
    cv_file = st.sidebar.file_uploader("PDF or DOCX", type=["pdf", "docx"], key="cv_upload")
    if cv_file is not None:
        if st.sidebar.button("Parse & ask to save"):
            try:
                data = upload_cv(cv_file.read(), cv_file.name)
                st.session_state.pending_confirmation = {
                    "confirmation_id": data["confirmation_id"],
                    "prompt": data["prompt"],
                    "tool_name": data.get("tool_name", "save_candidate"),
                }
                st.sidebar.success("Parsed. Confirm above to save to workspace.")
                st.rerun()
            except Exception as e:
                st.sidebar.error(str(e))

    # Job status
    st.sidebar.subheader("Ingestion jobs")
    for jid in st.session_state.job_ids[:5]:
        try:
            job = get_job(jid)
            st.sidebar.caption(f"Job {jid[:8]}... → {job.get('status', '?')}")
        except Exception:
            st.sidebar.caption(f"Job {jid[:8]}...")

    # Workspace snapshot
    if st.sidebar.button("Refresh workspace"):
        try:
            ws = get_workspace()
            st.sidebar.json({"candidates": len(ws.get("candidates", [])), "repos": len(ws.get("repositories", []))})
        except Exception as e:
            st.sidebar.error(str(e))

    # Chat
    st.title("Chat")
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Ask about candidates, repos, or paste a GitHub URL..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        try:
            resp = post_chat(prompt)
            if resp.get("type") == "confirmation":
                st.session_state.pending_confirmation = {
                    "confirmation_id": str(resp["confirmation_id"]),
                    "prompt": resp.get("prompt", ""),
                    "tool_name": resp.get("tool_name"),
                }
                if resp.get("tool_name") == "ingest_github":
                    st.session_state.job_ids = st.session_state.job_ids  # will be set after confirm
                with st.chat_message("assistant"):
                    st.markdown(resp.get("prompt", "") + " (Use Yes/No above.)")
                st.session_state.messages.append({"role": "assistant", "content": resp.get("prompt", "")})
            else:
                content = resp.get("content", "")
                with st.chat_message("assistant"):
                    st.markdown(content)
                st.session_state.messages.append({"role": "assistant", "content": content})
        except Exception as e:
            st.session_state.messages.append({"role": "assistant", "content": f"Error: {e}"})
            with st.chat_message("assistant"):
                st.error(str(e))
        st.rerun()


if __name__ == "__main__":
    main()
