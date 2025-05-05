import gradio as gr
import os
from imxtoscraper import (
    get_image_page_links,
    get_direct_image_url,
    download_image,
    download_gallery,
)
import requests
from PIL import Image
from io import BytesIO
import shutil

# Shared session
session = requests.Session()

def get_thumbnail(img_url, size=(256, 256)):
    try:
        res = session.get(img_url, stream=True)
        res.raise_for_status()
        img = Image.open(BytesIO(res.content))
        img.thumbnail(size)
        return img
    except Exception as e:
        print(f"⚠️ Error creating thumbnail: {e}")
        return None

def handle_input(url, mode, delay, resume, zip_files):
    save_dir = "downloaded_images"
    os.makedirs(save_dir, exist_ok=True)

    session.headers.update({
        "User-Agent": "Mozilla/5.0",
    })

    thumbnails = []

    if mode == "Single Image":
        print("🔗 Treating input as direct image URL")
        filename = download_image(url, save_dir, 1, 1, session)
        if filename:
            thumb = get_thumbnail(url)
            return [thumb], gr.File(label="Downloaded", value=filename)
        return [], "❌ Failed to download image."

    elif mode == "Gallery":
        print("📂 Treating input as IMX Gallery URL")
        viewer_links = get_image_page_links(url, session)
        image_urls = [get_direct_image_url(link, session) for link in viewer_links]
        downloaded = []
        for idx, img_url in enumerate(image_urls, 1):
            if img_url:
                filepath = download_image(img_url, save_dir, idx, len(image_urls), session)
                downloaded.append(filepath)
                thumb = get_thumbnail(img_url)
                if thumb:
                    thumbnails.append(thumb)

        if zip_files:
            zip_path = f"{save_dir}.zip"
            shutil.make_archive(save_dir, 'zip', save_dir)
            return thumbnails, zip_path
        else:
            return thumbnails, "✅ Downloaded without ZIP."

    else:
        return [], "❌ Unknown mode selected."

### GRADIO APP ###
demo = gr.Interface(
    fn=handle_input,
    inputs=[
        gr.Textbox(label="Image or Gallery URL"),
        gr.Radio(choices=["Single Image", "Gallery"], label="Mode", value="Gallery"),
        gr.Slider(label="Delay Between Requests", minimum=0.5, maximum=5.0, value=1.0, step=0.1),
        gr.Checkbox(label="Resume from Previous Download", value=False),
        gr.Checkbox(label="Zip All Images", value=True),
    ],
    outputs=[
        gr.Gallery(label="Downloaded Thumbnails" ,columns=5, height="auto"),
        gr.File(label="Download Zip or File"),
    ],
    title="🖼️ IMX Gallery/Image Downloader",
    description="Paste a direct image URL or a full IMX gallery. Choose mode and download images with preview thumbnails."
)

if __name__ == "__main__":
    demo.launch(share = True)
