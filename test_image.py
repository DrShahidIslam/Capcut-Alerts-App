import os
import sys

# Ensure local imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from publisher.featured_image import generate_featured_image

def test_image_generation():
    print("Testing image generation...")
    try:
        image_bytes = generate_featured_image("CapCut Video Stabilization Guide")
        
        is_png = image_bytes.startswith(b"\\x89PNG")
        ext = "png" if is_png else "jpg"
        
        filename = f"test_featured_image.{ext}"
        with open(filename, "wb") as f:
            f.write(image_bytes)
            
        print(f"Success! Image saved to {filename}")
        print(f"Size: {len(image_bytes)} bytes")
        print(f"Format: {'PNG (Fallback)' if is_png else 'JPEG (Gemini AI)'}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_image_generation()
