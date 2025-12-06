import io
import numpy as np
import cv2
from rembg import remove, new_session
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageChops

# Global variable for session (Lazy Loading)
session = None

def get_session():
    global session
    if session is None:
        session = new_session("u2netp")
    return session

def process_image(image_bytes):
    """
    Orchestrates the image processing pipeline:
    1. Background Removal
    2. Edge Refinement
    3. [NEW] Geometry (Deskew + Smart Framing)
    4. Lighting Enhancement
    5. Composition
    """
    
    # 1. Load Image
    original_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    
    # [OPTIMIZATION] Resize if too big to save RAM (prevent OOM on free tier)
    # iPhone photos are 3000/4000px, which kills the server. 1500px is enough for Vinted.
    max_dim = 1500
    if max(original_img.size) > max_dim:
        original_img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        
    original_size = original_img.size # (W, H)
    
    # 2. Remove Background
    # Ensure session is loaded
    sess = get_session()
    img_rgba = remove(original_img, session=sess) # Returns RGBA
    
    # 3. Refine Edges (Fix "sticker" look)
    img_refined = refine_edges(img_rgba)
    
    # [NEW] 3.5. Smart Geometry Pipeline
    # A. Deskew (Straighten)
    img_straight = deskew_image(img_refined)
    
    # B. Smart Framing (Center + 85% Height)
    # We pass original_size to try and respect the user's intended aspect ratio if possible,
    # or we can deliver a standard aspect. Let's default to a nice 3:4 or 1:1 if the original is weird,
    # but respecting original aspect is safest for mobile photos.
    img_framed = smart_frame(img_straight, target_aspect_ratio=original_size[0]/original_size[1])
    
    # 4. Enhance Lighting
    enhanced_img = enhance_lighting(img_framed)
    
    # 5. Composite over Custom Background
    final_img = composite_on_background_advanced(enhanced_img)
    
    # 6. Convert to bytes
    output_io = io.BytesIO()
    final_img.save(output_io, format='PNG')
    output_io.seek(0)
    
    return output_io

def deskew_image(img_rgba):
    """
    Rotates the image so the main object is vertically aligned.
    Uses cv2.minAreaRect.
    """
    # Convert to numpy
    img_np = np.array(img_rgba)
    alpha = img_np[:, :, 3]
    
    # Find contours
    contours, _ = cv2.findContours(alpha, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return img_rgba
    
    largest_contour = max(contours, key=cv2.contourArea)
    
    # Get rotated rectangle
    rect = cv2.minAreaRect(largest_contour)
    center, size, angle = rect
    
    # Normalize angle (minAreaRect returns -90 to 0 or 0 to 90 depending on version/opencv)
    # We want to correct slight tilts, e.g. +/- 20 degrees.
    # If angle is near -90, it means it's already vertical (opencv convention).
    
    rotation_angle = 0
    
    # Handle OpenCV angle quirks
    if size[0] < size[1]:
        # Height is greater than width, nominal "portrait" object
        if angle < -45:
             rotation_angle = -(90 + angle)
        else:
             rotation_angle = -angle
    else:
        # Width greater, 'landscape' object. 
        # If it's a shirt, it might be wide. 
        # Alignment logic is tricky without semantic knowledge.
        # Let's rely on the longer axis being vertical? No, shirts are wider.
        # If we assume clothes are usually "upright" in the photo and just slightly tilted:
        if -45 < angle < 45:
            rotation_angle = angle
    
    # Clamp rotation to avoid flipping valid horizontal items (like a belt or folded shirt)
    if abs(rotation_angle) > 20: 
        rotation_angle = 0 
        
    if rotation_angle != 0:
        return img_rgba.rotate(rotation_angle, resample=Image.Resampling.BICUBIC, expand=True)
    
    return img_rgba

def smart_frame(img_rgba, target_aspect_ratio):
    """
    Centers the object and scales it to occupy 85% of the canvas height.
    """
    # 1. Trim empty space (Crop to BBox)
    bbox = img_rgba.getbbox()
    if not bbox:
        return img_rgba
    img_cropped = img_rgba.crop(bbox)
    
    obj_w, obj_h = img_cropped.size
    
    # 2. Calculate Target Canvas Height
    # Rule: Object Height = 85% of Canvas Height
    # Canvas Height = Object Height / 0.85
    target_canvas_h = int(obj_h / 0.85)
    
    # 3. Calculate Target Canvas Width
    # Use the input aspect ratio to determine width
    target_canvas_w = int(target_canvas_h * target_aspect_ratio)
    
    # Verify width fits (Object width shouldn't exceed canvas width - padding)
    # If object is very wide, the 85% height rule might make it clip horizontally.
    # If obj_w > target_canvas_w * 0.9 (approx margins), we might need to scale based on width instead.
    if obj_w > target_canvas_w * 0.9:
        # Scale based on width: Object Width = 85% of Canvas Width
        target_canvas_w = int(obj_w / 0.85)
        target_canvas_h = int(target_canvas_w / target_aspect_ratio)
        # Recalculate if height constraint is violated? 
        # If we scale by width, the height percentage will be < 85%, which is safe (padding > 7.5%).
    
    # 4. Create Canvas
    canvas = Image.new("RGBA", (target_canvas_w, target_canvas_h), (0, 0, 0, 0))
    
    # 5. Paste Center
    x_pos = (target_canvas_w - obj_w) // 2
    y_pos = (target_canvas_h - obj_h) // 2
    
    canvas.paste(img_cropped, (x_pos, y_pos))
    
    return canvas

def refine_edges(img_rgba):
    """
    Refines the alpha mask to remove jagged edges and halos.
    """
    img_np = np.array(img_rgba)
    alpha = img_np[:, :, 3]
    
    # Erode slighty less aggressive to update quality
    kernel = np.ones((3, 3), np.uint8)
    alpha_eroded = cv2.erode(alpha, kernel, iterations=1)
    
    # Blur
    alpha_blurred = cv2.GaussianBlur(alpha_eroded, (3, 3), 0)
    
    img_np[:, :, 3] = alpha_blurred
    return Image.fromarray(img_np)

def enhance_lighting(img_rgba):
    """
    Applies lighting adjustments. 
    """
    img = img_rgba.copy()
    
    # 1. Increase Brightness (Exposure)
    enhancer_brightness = ImageEnhance.Brightness(img)
    img = enhancer_brightness.enhance(1.05)
    
    # 2. Enhance Contrast
    enhancer_contrast = ImageEnhance.Contrast(img)
    img = enhancer_contrast.enhance(1.1)
    
    # 3. Saturation (Make clothes pop)
    enhancer_color = ImageEnhance.Color(img)
    img = enhancer_color.enhance(1.15)
    
    # 4. Sharpen
    img = img.filter(ImageFilter.SHARPEN)
    
    return img

def composite_on_background_advanced(fg_rgba):
    """
    Composites the RGBA image over 'background.jpg' with realistic shadows.
    """
    try:
        bg_source = Image.open("background.jpg").convert("RGB")
    except FileNotFoundError:
        print("Background.jpg not found, using solid color.")
        bg_source = Image.new("RGB", fg_rgba.size, (245, 245, 245))

    # Resize background to cover foreground dimensions
    bg = ImageOps.fit(bg_source, fg_rgba.size, method=Image.Resampling.LANCZOS)
    
    # --- Shadow Generation ---
    # We want two shadows for realism:
    # 1. Contact Shadow: Dark, sharp, close to the object (grounding).
    # 2. Ambient Shadow: Lighter, very blurred, further away (diffuse light).
    
    # Extract alpha mask for shadow generation
    mask = fg_rgba.split()[3]
    
    # Create blank canvas for shadows
    canvas_width, canvas_height = fg_rgba.size
    
    # 1. Ambient Shadow (The "Softbox" cast)
    off_x_amb, off_y_amb = int(canvas_width * 0.02), int(canvas_height * 0.04)
    ambient_shadow = Image.new("RGBA", (canvas_width, canvas_height), (0,0,0,0))
    ambient_shadow.paste((0,0,0, 80), (off_x_amb, off_y_amb), mask=mask)
    ambient_shadow = ambient_shadow.filter(ImageFilter.GaussianBlur(radius=15))
    
    # 2. Contact Shadow (Grounding)
    off_y_con = int(canvas_height * 0.01)
    contact_shadow = Image.new("RGBA", (canvas_width, canvas_height), (0,0,0,0))
    contact_shadow.paste((0,0,0, 140), (0, off_y_con), mask=mask)
    contact_shadow = contact_shadow.filter(ImageFilter.GaussianBlur(radius=4))
    
    # Combine shadows onto background
    bg.paste(ambient_shadow, (0,0), ambient_shadow)
    bg.paste(contact_shadow, (0,0), contact_shadow)
    
    # --- Foreground Composition ---
    bg.paste(fg_rgba, (0, 0), fg_rgba)
    
    return bg
