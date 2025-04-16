# IMX Gallery Downloader for Google Colab
# Step 1: Install required packages if not already available in Colab
# Note: Your output shows these are already installed, so this is just for completeness
!pip install requests beautifulsoup4

# Step 2: Create the downloader script directly in Python (avoiding magic commands)
import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import time
import random
import json
from google.colab import files
import argparse
import sys

# CONFIG
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
    
    # Based on your HTML snippets, we're looking for links inside elements with class 'tooltip'
    a_tags = soup.select('.tooltip a')
    viewer_links = [a['href'] for a in a_tags if a and a.has_attr('href') and a['href'].startswith('https://imx.to/i/')]
    
    if not viewer_links:
        # Fallback approach for different HTML structures
        a_tags = soup.select('a[href^="https://imx.to/i/"]')
        viewer_links = [a['href'] for a in a_tags if a and a.has_attr('href')]
    
    print(f"✅ Found {len(viewer_links)} image viewer pages.")
    return viewer_links

def get_direct_image_url(viewer_url, session):
    print(f"➡️  Opening viewer page: {viewer_url}")
    res = session.get(viewer_url)
    res.raise_for_status()
    
    soup = BeautifulSoup(res.text, 'html.parser')
    
    # Handle the initial form submission if present
    form = soup.find("form", {"method": "POST"})
    if form:
        print("📝 Found a form to submit...")
        post_url = urljoin(viewer_url, form.get("action", ""))
        
        # Get all input fields including hidden ones
        inputs = form.find_all("input")
        form_data = {
            input_tag.get("name"): input_tag.get("value", "") 
            for input_tag in inputs 
            if input_tag.get("name")
        }
        
        # Submit the form
        print(f"↪️  Submitting form to: {post_url}")
        res = session.post(post_url, data=form_data)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
    
    # Extract the image URL
    # First try to find an image within the centered class as shown in your HTML
    img_tag = soup.find("img", {"class": "centred"})
    if not img_tag:
        # Try other common patterns
        img_tag = soup.find("img", {"id": "image"})
    
    if not img_tag:
        # Last resort: find any img tag that might be the main image
        img_candidates = soup.find_all("img")
        for img in img_candidates:
            # Look for images with certain attributes that suggest they're the main content
            # This is a heuristic based on your HTML examples
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
    
    # Make sure filename has an extension
    if not os.path.splitext(filename)[1]:
        filename += ".jpg"  # Default to jpg if no extension
        
    filepath = os.path.join(save_dir, filename)
    
    # Skip if file already exists
    if os.path.exists(filepath):
        print(f"⏭️  [{index}/{total}] File already exists: {filename}")
        return filepath
    
    print(f"📥 [{index}/{total}] Downloading: {filename}")
    
    try:
        res = session.get(image_url, stream=True)
        res.raise_for_status()
        
        # Create directory if it doesn't exist
        os.makedirs(save_dir, exist_ok=True)
        
        # Save the image
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
    """Create a zip file of all downloaded images (for Colab)"""
    zip_path = f"{save_dir}.zip"
    print(f"📦 Creating zip file at {zip_path}...")
    
    # Use shell command to create zip
    os.system(f"zip -r {zip_path} {save_dir}")
    
    print(f"✅ Zip file created: {zip_path}")
    return zip_path

def download_gallery(gallery_url, output_dir="downloaded_images", delay=1.0, resume=False, create_zip_file=True):
    """Main function to download a gallery"""
    save_dir = output_dir
    
    # Create session for maintaining cookies and connection
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    
    # Ensure save directory exists
    os.makedirs(save_dir, exist_ok=True)
    
    # Track progress
    completed = []
    viewer_links = []
    
    # Load progress if resuming
    if resume:
        progress = load_progress(save_dir)
        if progress:
            completed = progress.get("completed", [])
            viewer_links = progress.get("viewer_links", [])
            print(f"📋 Resuming download: {len(completed)}/{len(viewer_links)} already completed")
    
    # Get viewer links if not resuming or if we don't have them from previous run
    if not viewer_links:
        viewer_links = get_image_page_links(gallery_url, session)
        if not viewer_links:
            print("❌ No image links found in the gallery. Check the URL or website structure.")
            return
    
    total = len(viewer_links)
    start_time = time.time()
    
    print(f"🚀 Starting download of {total} images to {save_dir}")
    
    # Download each image
    for idx, viewer_url in enumerate(viewer_links, start=1):
        # Skip if already completed
        if viewer_url in completed:
            print(f"⏭️  [{idx}/{total}] Already downloaded: {viewer_url}")
            continue
        
        try:
            # Random delay to avoid triggering anti-scraping measures
            sleep_time = delay * (0.5 + random.random())
            time.sleep(sleep_time)
            
            # Get direct image URL and download
            direct_url = get_direct_image_url(viewer_url, session)
            if direct_url:
                filepath = download_image(direct_url, save_dir, idx, total, session)
                if filepath:
                    completed.append(viewer_url)
                    
                    # Save progress every 5 downloads
                    if idx % 5 == 0:
                        save_progress(save_dir, completed, viewer_links)
                        
        except Exception as e:
            print(f"❌ Error processing {viewer_url}: {e}")
        
        # Show progress
        elapsed = time.time() - start_time
        remaining = (elapsed / idx) * (total - idx) if idx > 0 else 0
        print(f"⏱️  Progress: {idx}/{total} ({idx/total*100:.1f}%) | " 
              f"Elapsed: {elapsed/60:.1f}m | Est. remaining: {remaining/60:.1f}m")
    
    # Save final progress
    save_progress(save_dir, completed, viewer_links)
    
    # Create zip file if requested (Colab specific)
    if create_zip_file and completed:
        zip_path = create_zip(save_dir)
        print(f"📦 Zip file created: {zip_path}")
        print("Use the following cell to download the zip:")
        print("from google.colab import files; files.download('downloaded_images.zip')")
    
    # Final stats
    elapsed = time.time() - start_time
    print(f"🎉 Downloaded {len(completed)}/{total} images in {elapsed/60:.1f} minutes")
    print(f"📁 Files saved to: {os.path.abspath(save_dir)}")
    
    return save_dir
