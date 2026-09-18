import os
import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")
UPLOAD_ENDPOINT = f"{API_URL}/uploadfile/"
PHOTOS_ENDPOINT = f"{API_URL}/photos"
REQUEST_TIMEOUT = 60  

st.set_page_config(page_title="Photo Feed", page_icon=":material/filter_drama:")
st.title("CloudSnap")

with st.container(border=True):
    st.subheader("Upload a photo")

    with st.form("upload_form", clear_on_submit=True):
        uploaded_file = st.file_uploader(
            "Choose a file",
            type=["jpg", "jpeg", "png", "webp"],
            max_upload_size=25,
        )
        caption = st.text_input("Caption", placeholder="Write a caption...")
        submitted = st.form_submit_button("Upload", type="primary")

    if submitted:
        if uploaded_file is None:
            st.error("Please choose a file first.")
        else:
            with st.spinner("Uploading..."):
                try:
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                    data = {"caption": caption}
                    response = requests.post(
                        UPLOAD_ENDPOINT, files=files, data=data, timeout=REQUEST_TIMEOUT
                    )
                    response.raise_for_status()
                    resp_data = response.json()
                    st.success(f"Uploaded — {resp_data.get('caption') or 'no caption'}")
                    st.rerun()
                except requests.exceptions.Timeout:
                    st.error("Upload timed out. Try again.")
                except requests.exceptions.ConnectionError:
                    st.error("Can't reach the API. Check API_URL and that the backend is running.")
                except requests.exceptions.HTTPError:
                    st.error(f"Upload failed ({response.status_code}): {response.text}")
                except Exception as e:
                    st.error(f"Unexpected error: {e}")

st.divider()

st.subheader("Feed")
with st.container(border=True):

    try:
        feed_response = requests.get(PHOTOS_ENDPOINT, timeout=REQUEST_TIMEOUT)
        feed_response.raise_for_status()
        photos = feed_response.json()
    except Exception as e:
        photos = []
        st.error(f"Couldn't load feed: {e}")

    if not photos:
        st.info("No photos yet. Upload one above!")

    for photo in photos:
        photo_id = photo["id"]
        st.image(photo["url"], width="stretch")
        if photo.get("caption"):
            st.write(photo["caption"])

        with st.expander("Comments"):
            try:
                c_resp = requests.get(f"{PHOTOS_ENDPOINT}/{photo_id}/comments", timeout=REQUEST_TIMEOUT)
                c_resp.raise_for_status()
                comments = c_resp.json()
            except Exception as e:
                comments = []
                st.error(f"Couldn't load comments: {e}")

            for c in comments:
                st.write(f"💬 {c['text']}")

            with st.form(key=f"comment_form_{photo_id}", clear_on_submit=True):
                new_comment = st.text_input("Add a comment", key=f"comment_input_{photo_id}")
                posted = st.form_submit_button("Post")

            if posted and new_comment.strip():
                try:
                    requests.post(
                        f"{PHOTOS_ENDPOINT}/{photo_id}/comments",
                        json={"text": new_comment},
                        timeout=REQUEST_TIMEOUT,
                    ).raise_for_status()
                    st.rerun()  
                except Exception as e:
                    st.error(f"Couldn't post comment: {e}")

    st.divider()
