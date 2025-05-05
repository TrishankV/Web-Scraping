import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import time
import random
import json

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def get_image_page_links(gallery_url, session):
    print(f"🔍 Fetching gallery page: {gallery_url}")
    res = session.get(gallery_url)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, 'html.parser')

    a_tags = soup.select('.tooltip a')
    viewer_links = [a['href'] for a in a_tags if a.has_attr('href') and a['href'].startswith('https://imx.to/i/')]

    if not viewer_links:
        a_tags = soup.select('a[href^="https://imx.to/i/"]')
        viewer_links = [a['href'] for a in a_tags if a.has_attr('href')]

    print(f"✅ Found {len(viewer_links)} image viewer pages.")
    return viewer_links


def get_direct_image_url(viewer_url, session):
    print(f"➡️  Opening viewer page: {viewer_url}")
    res = session.get(viewer_url)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, 'html.parser')

    form = soup.find("form", {"method": "POST"})
    if form:
        print("📝 Found a form to submit...")
        post_url = urljoin(viewer_url, form.get("action", ""))
        inputs = form.find_all("input")
        form_data = {
            input_tag.get("name"): input_tag.get("value", "")
            for input_tag in inputs
            if input_tag.get("name")
        }

        print(f"↪️  Submitting form to: {post_url}")
        res = session.post(post_url, data=form_data)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')

    img_tag = soup.find("img", {"class": "centred"}) or soup.find("img", {"id": "image"})
    if not img_tag:
        for img in soup.find_all("img"):
            if (img.get("style") and "max-width" in img.get("style")) or \
               (img.get("class") and "centred" in img.get("class")):
                img_tag = img
                break

    if img_tag and img_tag.get("src"):
        img_url = img_tag["src"]
        if not img_url.startswith(("http:", "https:")):
            img_url = urljoin(viewer_url, img_url)
        print(f"✅ Found image URL: {img_url}")
        return img_url

    print("⚠️ Could not find image URL")
    return None


def download_image(image_url, save_dir, index, total, session):
    filename = os.path.basename(image_url)
    if not os.path.splitext(filename)[1]:
        filename += ".jpg"

    filepath = os.path.join(save_dir, filename)

    if os.path.exists(filepath):
        print(f"⏭️  [{index}/{total}] File already exists: {filename}")
        return filepath

    print(f"📥 [{index}/{total}] Downloading: {filename}")

    try:
        res = session.get(image_url, stream=True)
        res.raise_for_status()
        os.makedirs(save_dir, exist_ok=True)

        with open(filepath, 'wb') as f:
            for chunk in res.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        print(f"✔️  Saved to {filepath}")
        return filepath
    except Exception as e:
        print(f"❌ Failed to download {filename}: {e}")
        return None


def save_progress(save_dir, completed, viewer_links):
    progress_file = os.path.join(save_dir, "download_progress.json")
    with open(progress_file, 'w') as f:
        json.dump({
            "completed": completed,
            "viewer_links": viewer_links,
            "timestamp": time.time()
        }, f)


def load_progress(save_dir):
    progress_file = os.path.join(save_dir, "download_progress.json")
    if os.path.exists(progress_file):
        with open(progress_file, 'r') as f:
            return json.load(f)
    return None


def create_zip(save_dir):
    zip_path = f"{save_dir}.zip"
    print(f"📦 Creating zip file at {zip_path}...")
    os.system(f"zip -r -q '{zip_path}' '{save_dir}'")
    print(f"✅ Zip file created: {zip_path}")
    return zip_path


def download_gallery(gallery_url, output_dir="downloaded_images", delay=1.0, resume=False, create_zip_file=True):
    save_dir = output_dir
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    os.makedirs(save_dir, exist_ok=True)

    completed = []
    viewer_links = []

    if resume:
        progress = load_progress(save_dir)
        if progress:
            completed = progress.get("completed", [])
            viewer_links = progress.get("viewer_links", [])
            print(f"📋 Resuming download: {len(completed)}/{len(viewer_links)} already completed")

    if not viewer_links:
        viewer_links = get_image_page_links(gallery_url, session)
        if not viewer_links:
            print("❌ No image links found.")
            return save_dir

    total = len(viewer_links)
    start_time = time.time()
    print(f"🚀 Starting download of {total} images to {save_dir}")

    for idx, viewer_url in enumerate(viewer_links, start=1):
        if viewer_url in completed:
            continue

        try:
            time.sleep(delay * (0.5 + random.random()))
            direct_url = get_direct_image_url(viewer_url, session)
            if direct_url:
                filepath = download_image(direct_url, save_dir, idx, total, session)
                if filepath:
                    completed.append(viewer_url)
                    if idx % 5 == 0:
                        save_progress(save_dir, completed, viewer_links)
        except Exception as e:
            print(f"❌ Error processing {viewer_url}: {e}")

        elapsed = time.time() - start_time
        remaining = (elapsed / idx) * (total - idx)
        print(f"⏱️  Progress: {idx}/{total} "
              f"({idx/total*100:.1f}%) | Elapsed: {elapsed/60:.1f}m | Remaining: {remaining/60:.1f}m")

    save_progress(save_dir, completed, viewer_links)

    zip_path = None
    if create_zip_file and completed:
        zip_path = create_zip(save_dir)

    print(f"🎉 Finished downloading {len(completed)}/{total} images.")
    print(f"📁 Output directory: {os.path.abspath(save_dir)}")
    if zip_path:
        print(f"📦 Zip file available at: {os.path.abspath(zip_path)}")

    return save_dir


def run_downloader(gallery_url, delay=1.0, resume=False, zip_files=True):
    return download_gallery(
        gallery_url=gallery_url,
        output_dir="downloaded_images",
        delay=delay,
        resume=resume,
        create_zip_file=zip_files
    )
