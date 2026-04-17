import pygame
import math
import random
import threading
import time

MANUAL_INGEST_CMD = pygame.USEREVENT + 1

class ContextCard:
    def __init__(self, card_type: str, content: str, surface=None, label=""):
        self.card_type = card_type  # "TEXT", "CODE", "IMAGE", "WEB"
        self.content = content
        self.surface = surface
        self.label = label

class WebResultCard(ContextCard):
    def __init__(self, url: str, status: str = "running"):
        super().__init__("WEB", "Initializing stealth bridge...", label="Web Agent")
        self.url = url
        self.status = status
        self.favicon_surf = None
        self._fetch_favicon()
        
    def _fetch_favicon(self):
        import urllib.parse
        parsed = urllib.parse.urlparse(self.url)
        domain = f"{parsed.scheme}://{parsed.netloc}"
        favicon_url = f"https://www.google.com/s2/favicons?domain={domain}&sz=32"
        def fetch_thread():
            try:
                import requests, io, pygame
                r = requests.get(favicon_url, timeout=5)
                if r.status_code == 200:
                    img = pygame.image.load(io.BytesIO(r.content)).convert_alpha()
                    self.favicon_surf = img
            except Exception: pass
        import threading
        threading.Thread(target=fetch_thread, daemon=True).start()

class NeuralVisualizer:
    def __init__(self, width=800, height=600, num_nodes=120):
        self.width = width
        self.height = height
        self.num_nodes = num_nodes
        self.nodes = []
        self.running = False
        self.state = "STANDBY"
        self.is_fullscreen = False

        # UI Tuning
        self.base_radius = 200
        self.current_radius = 200
        self.target_radius = 200
        self.angle_x = 0.0
        self.angle_y = 0.0

        # Subtitle state -- written from the main thread via
        # set_subtitle_text(), read from the UI thread during render.
        # Python string assignment is atomic, but the lock lets us
        # extend this later (wrapping, queues) without rework.
        self._subtitle_lock = threading.Lock()
        self._subtitle_text = ""
        self._user_text = ""
        self._text_time = 0.0
        
        # Background task indicator
        self._bg_task_lock = threading.Lock()
        self._bg_task_text = ""
        
        # Context Wing Setup
        self.wing_open_ratio = 0.0
        self.target_wing_open_ratio = 0.0
        self.context_cards = []
        self.y_scroll = 0.0
        self.scroll_velocity = 0.0
        self.is_dragging_wing = False
        self.last_mouse_y = 0
        self.hover_active = False
        
        self.sphere_pulse_overclock = 1.0
        
        # Fibonacci Sphere Math
        phi = math.pi * (3.0 - math.sqrt(5.0)) 
        for i in range(self.num_nodes):
            y = 1 - (i / float(self.num_nodes - 1)) * 2 
            radius = math.sqrt(1 - y * y)
            theta = phi * i
            x = math.cos(theta) * radius
            z = math.sin(theta) * radius
            self.nodes.append([x, y, z])

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False

    def set_state(self, new_state):
        self.state = new_state.upper()

    def set_subtitle_text(self, text):
        """Thread-safe: queue text to appear as a subtitle on the sphere."""
        with self._subtitle_lock:
            self._subtitle_text = str(text) if text is not None else ""
            self._text_time = time.time()

    def set_user_text(self, text):
        with self._subtitle_lock:
            self._user_text = str(text) if text is not None else ""
            self._text_time = time.time()

    def set_bg_task(self, text):
        with self._bg_task_lock:
            self._bg_task_text = str(text) if text is not None else ""

    def toggle_fullscreen(self, screen):
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            # Grab the native monitor resolution and go borderless
            info = pygame.display.Info()
            self.width, self.height = info.current_w, info.current_h
            return pygame.display.set_mode((self.width, self.height), pygame.FULLSCREEN)
        else:
            # Revert to standard window
            self.width, self.height = 800, 600
            return pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)

    def _draw_dashed_rect(self, screen, color, rect, width, dash_length):
        x, y, w, h = rect
        pts = []
        for i in range(x, x+w, dash_length*2): pts.append(((i, y), (min(i+dash_length, x+w), y)))
        for i in range(x, x+w, dash_length*2): pts.append(((i, y+h), (min(i+dash_length, x+w), y+h)))
        for i in range(y, y+h, dash_length*2): pts.append(((x, i), (x, min(i+dash_length, y+h))))
        for i in range(y, y+h, dash_length*2): pts.append(((x+w, i), (x+w, min(i+dash_length, y+h))))
        for p1, p2 in pts:
            pygame.draw.line(screen, color, p1, p2, width)

    def _run_loop(self):
        pygame.init()
        pygame.font.init()
        subtitle_font = pygame.font.SysFont("Segoe UI,Arial,sans-serif", 24, bold=False)
        mono_font = pygame.font.SysFont("Consolas,Courier New,monospace", 16)
        screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)
        pygame.display.set_caption("Friday Neural Core")
        clock = pygame.time.Clock()

        # Force Windows Always On Top seamlessly
        try:
            import ctypes
            hwnd = pygame.display.get_wm_info()["window"]
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002)
        except Exception:
            pass

        BG_COLOR = (10, 12, 16)
        NODE_COLOR = (120, 200, 255)
        LINE_COLOR = (40, 80, 120)
        SUBTITLE_COLOR = (220, 235, 255)
        SUBTITLE_BG = (5, 8, 12)

        while self.running:
            # --- CRITICAL FIX: The Event Pump ---
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_f: # Press 'F' to go Fullscreen
                        screen = self.toggle_fullscreen(screen)
                    elif event.key == pygame.K_ESCAPE and self.is_fullscreen: # ESC to exit
                        screen = self.toggle_fullscreen(screen)
                elif event.type == pygame.VIDEORESIZE and not self.is_fullscreen:
                    # Dynamically adjust center if window is dragged/resized
                    self.width, self.height = event.w, event.h
                    screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)
                elif event.type == getattr(pygame, "DROPBEGIN", 4104):  # handle older pygame bindings safely
                    self.target_wing_open_ratio = 1.0
                    self.hover_active = True
                elif event.type == getattr(pygame, "DROPCOMPLETE", 4105):
                    self.hover_active = False
                    # Only close if we didn't actually lock a file in
                    if not self.context_cards:
                        self.target_wing_open_ratio = 0.0
                elif event.type == pygame.DROPFILE:
                    self.target_wing_open_ratio = 1.0
                    self.hover_active = False
                    import action_engine
                    action_engine.ActionExecutor.process_multimodal_input(event.file)
                elif event.type == MANUAL_INGEST_CMD:
                    self.target_wing_open_ratio = 1.0
                    self.sphere_pulse_overclock = 2.0
                    import clipboard_engine
                    
                    clip_data = clipboard_engine.get_active_clipboard_data()
                    if clip_data:
                        if clip_data["type"] == "text":
                            self.context_cards.append(ContextCard("CODE", clip_data["content"], label="Syntax Detection"))
                            try:
                                import memory_vault
                                memory_vault.index_data(clip_data["content"], "clipboard_text")
                            except: pass
                        elif clip_data["type"] == "image":
                            import io, base64
                            pil_img = clip_data["content"]
                            if pil_img.mode in ("RGBA", "P"):
                                pil_img = pil_img.convert("RGB")
                            
                            buf = io.BytesIO()
                            pil_img.save(buf, format="JPEG")
                            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                            
                            py_str = pil_img.tobytes()
                            surf = pygame.image.fromstring(py_str, pil_img.size, pil_img.mode)
                            self.context_cards.append(ContextCard("IMAGE", b64, surface=surf, label="Apex Border"))
                elif event.type == pygame.MOUSEWHEEL:
                    if self.wing_open_ratio > 0:
                        self.scroll_velocity += event.y * 30
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if self.wing_open_ratio > 0.5:
                        x, y = event.pos
                        wing_start_x = int(self.width * 0.7)
                        if x > wing_start_x:
                            self.is_dragging_wing = True
                            self.last_mouse_y = y
                            self.scroll_velocity = 0
                elif event.type == pygame.MOUSEBUTTONUP:
                    self.is_dragging_wing = False
                elif event.type == pygame.MOUSEMOTION:
                    if self.is_dragging_wing:
                        dy = event.pos[1] - self.last_mouse_y
                        self.y_scroll += dy
                        self.scroll_velocity = dy
                        self.last_mouse_y = event.pos[1]

            screen.fill(BG_COLOR)
            
            # Wing Kinetics
            target = 1.0 if self.hover_active else self.target_wing_open_ratio
            self.wing_open_ratio += (target - self.wing_open_ratio) * 0.15
            if not self.is_dragging_wing:
                self.y_scroll += self.scroll_velocity
                self.scroll_velocity *= 0.92
                
            if self.sphere_pulse_overclock > 1.0:
                self.sphere_pulse_overclock += (1.0 - self.sphere_pulse_overclock) * 0.1
            
            # State Logic
            t = time.time()
            if self.state == "STANDBY":
                self.target_radius = self.base_radius + math.sin(t * 2) * 10
                rotation_speed = 0.01
            elif self.state == "THINKING":
                self.target_radius = self.base_radius + 40
                rotation_speed = 0.04
            elif self.state == "TALKING":
                import state
                amp_obj = state.current_volume
                amp = amp_obj.value if hasattr(amp_obj, 'value') else float(amp_obj or 0.0)
                
                # Map amp (0 to ~32768) to radius extension
                visual_amp = min(amp / 150, 80)
                
                self.target_radius = self.base_radius + visual_amp * self.sphere_pulse_overclock
                rotation_speed = 0.08
                
            # Slow down interpolation (0.05) for "liquid" movement
            self.current_radius += (self.target_radius - self.current_radius) * 0.05
            self.angle_y += rotation_speed
            self.angle_x += rotation_speed * 0.5

            sin_x, cos_x = math.sin(self.angle_x), math.cos(self.angle_x)
            sin_y, cos_y = math.sin(self.angle_y), math.cos(self.angle_y)

            projected_2d = []
            
            # 3D Math
            for node in self.nodes:
                x, y, z = node[0], node[1], node[2]
                xy = cos_x * y - sin_x * z
                xz = sin_x * y + cos_x * z
                yz = cos_y * xz - sin_y * x
                yx = sin_y * xz + cos_y * x

                final_x = yx * self.current_radius
                final_y = xy * self.current_radius
                final_z = yz * self.current_radius

                z_offset = final_z + 400 
                if z_offset <= 0: z_offset = 0.1
                factor = 400 / z_offset
                
                # Shift center dynamically if Wing is actively projecting
                target_center_x = (self.width * 0.7) / 2
                base_center_x = self.width / 2
                actual_center_x = base_center_x - (base_center_x - target_center_x) * self.wing_open_ratio
                
                screen_x = int(actual_center_x + final_x * factor)
                screen_y = int(self.height / 2 + final_y * factor)
                
                projected_2d.append((screen_x, screen_y, final_z))

            threshold_sq = (self.current_radius * 0.45) ** 2 
            for i in range(len(projected_2d)):
                for j in range(i + 1, len(projected_2d)):
                    p1, p2 = projected_2d[i], projected_2d[j]
                    dist_sq = (p1[0]-p2[0])**2 + (p1[1]-p2[1])**2 + (p1[2]-p2[2])**2
                    
                    if dist_sq < threshold_sq:
                        depth_fade = max(10, min(255, int((p1[2] + p2[2] + 200) / 2)))
                        color = (int(LINE_COLOR[0] * depth_fade/255), 
                                 int(LINE_COLOR[1] * depth_fade/255), 
                                 int(LINE_COLOR[2] * depth_fade/255))
                        pygame.draw.line(screen, color, (p1[0], p1[1]), (p2[0], p2[1]), 1)

            for p in projected_2d:
                size = max(1, int(3 + (p[2] / 100))) 
                pygame.draw.circle(screen, NODE_COLOR, (p[0], p[1]), size)

            with self._subtitle_lock:
                friday_txt = self._subtitle_text
                user_txt = self._user_text
                txt_time = self._text_time
            
            elapsed = t - txt_time
            if elapsed < 6.0:
                alpha = 255 if elapsed <= 5.0 else max(0, int(255 * (6.0 - elapsed)))
                self.render_subtitles(friday_txt, user_txt, screen, subtitle_font, (255, 255, 255), alpha)

            # --- Background Pulse Indicator ---
            with self._bg_task_lock:
                bg_txt = self._bg_task_text
            
            if bg_txt:
                # Oscillate alpha between ~50 and 255
                pulse_alpha = int(150 + 105 * math.sin(t * 4))
                bg_surf = subtitle_font.render(bg_txt, True, (120, 200, 255))
                shadow = subtitle_font.render(bg_txt, True, (0, 0, 0))
                bg_surf.set_alpha(pulse_alpha)
                shadow.set_alpha(pulse_alpha)
                
                # Render top-right
                x_pos = self.width - bg_surf.get_width() - 20
                if self.wing_open_ratio > 0:
                    x_pos -= int(self.width * 0.3 * self.wing_open_ratio)
                y_pos = 20
                screen.blit(shadow, (x_pos + 2, y_pos + 2))
                screen.blit(bg_surf, (x_pos, y_pos))

            self.draw_wing(screen, subtitle_font, mono_font)

            pygame.display.flip()
            clock.tick(60) 

        pygame.quit()

    # ---- Wing Layer --------------------------------------------------------

    def draw_wing(self, screen, font, mono_font):
        if self.wing_open_ratio < 0.01:
            return
        
        wing_w = int(self.width * 0.3)
        wing_x = self.width - int(wing_w * self.wing_open_ratio)
        
        # Draw background glassmorphism Pygame fake-blur
        bg_rect = pygame.Rect(wing_x, 0, wing_w, self.height)
        bg_rect = screen.get_rect().clip(bg_rect)
        if bg_rect.width > 0 and bg_rect.height > 0:
            try:
                bg_snap = screen.subsurface(bg_rect).copy()
                small_size = (max(1, bg_rect.width // 8), max(1, bg_rect.height // 8))
                downscaled = pygame.transform.smoothscale(bg_snap, small_size)
                blurred = pygame.transform.smoothscale(downscaled, (bg_rect.width, bg_rect.height))
                screen.blit(blurred, (bg_rect.x, bg_rect.y))
            except ValueError:
                pass
                
        overlay = pygame.Surface((wing_w, self.height), pygame.SRCALPHA)
        overlay.fill((10, 10, 15, 180))
        screen.blit(overlay, (wing_x, 0))
        
        # Clipping rect
        old_clip = screen.get_clip()
        screen.set_clip((wing_x, 0, wing_w, self.height))
        
        card_margin = 15
        current_y = int(self.y_scroll) + card_margin
        
        if not self.context_cards:
            # Draw Dashed drop zone
            drop_h = 150
            drop_rect = pygame.Rect(wing_x + card_margin, self.height//2 - drop_h//2, wing_w - 2 * card_margin, drop_h)
            self._draw_dashed_rect(screen, (80, 90, 100), drop_rect, 2, 8)
            # drop shadow text
            drop_text1_s = font.render("Drop file to analyze", True, (0, 0, 0))
            drop_text1 = font.render("Drop file to analyze", True, (200, 200, 200))
            drop_pos_x = drop_rect.centerx - drop_text1.get_width() // 2
            drop_pos_y = drop_rect.centery - drop_text1.get_height() // 2
            screen.blit(drop_text1_s, (drop_pos_x+2, drop_pos_y+2))
            screen.blit(drop_text1, (drop_pos_x, drop_pos_y))
        
        for card in self.context_cards:
            if card.card_type == "WEB":
                import time, math
                target_font = font
                lines = ["[ WEB AGENT ]", "-" * 30, card.url, "Status: " + ("Active Scanning..." if card.status == "running" else "Complete")]
                for para in card.content.split('\n')[:6]:
                    lines.append(para[:120])
                    
                block_h = len(lines) * target_font.get_linesize() + 2 * card_margin
                card_rect = pygame.Rect(wing_x + card_margin, current_y, wing_w - 2 * card_margin, block_h)
                pygame.draw.rect(screen, (20, 25, 30), card_rect, border_radius=8)
                
                # Neural Wave Web border
                if card.status == "running":
                    alpha = int((math.sin(time.time() * 5) + 1.0) * 127)
                    wave_surf = pygame.Surface((card_rect.width, card_rect.height), pygame.SRCALPHA)
                    pygame.draw.rect(wave_surf, (0, 212, 255, alpha), wave_surf.get_rect(), width=2, border_radius=8)
                    screen.blit(wave_surf, card_rect.topleft)
                else:
                    pygame.draw.rect(screen, (100, 255, 150), card_rect, width=2, border_radius=8)
                    
                if getattr(card, "favicon_surf", None):
                    screen.blit(card.favicon_surf, (wing_x + card_margin + 8, current_y + 8))
                    text_x_offset = 48
                else:
                    text_x_offset = 12
                    
                for i, line in enumerate(lines):
                    txt_surf = target_font.render(line, True, (200, 200, 200) if i > 3 else (150, 200, 255))
                    screen.blit(txt_surf, (wing_x + card_margin + text_x_offset if i < 3 else wing_x + card_margin * 2, current_y + card_margin + i * target_font.get_linesize()))

                if card_rect.collidepoint(pygame.mouse.get_pos()):
                    tools_text_s = font.render("[ Trash ]   [ Extract ]   [ Sandbox ]", True, (0, 0, 0))
                    tools_text = font.render("[ Trash ]   [ Extract ]   [ Sandbox ]", True, (255, 255, 255))
                    t_x = card_rect.right - tools_text.get_width() - 8
                    t_y = card_rect.bottom - tools_text.get_height() - 8
                    screen.blit(tools_text_s, (t_x+2, t_y+2))
                    screen.blit(tools_text, (t_x, t_y))
                current_y += block_h + card_margin
                
            elif card.card_type == "IMAGE" and card.surface:
                img_h = int((wing_w - 2*card_margin) * (card.surface.get_height() / card.surface.get_width()))
                img_surf = pygame.transform.smoothscale(card.surface, (wing_w - 2*card_margin, img_h))
                
                if card.label == "Apex Border":
                    pygame.draw.rect(screen, (0, 212, 255), (wing_x + card_margin - 2, current_y - 2, wing_w - 2 * card_margin + 4, img_h + 4), border_radius=4)
                    
                screen.blit(img_surf, (wing_x + card_margin, current_y))
                
                card_rect = pygame.Rect(wing_x + card_margin, current_y, wing_w - 2 * card_margin, img_h)
                if card_rect.collidepoint(pygame.mouse.get_pos()):
                    # Command Deck Hover Element
                    tools_text_s = font.render("[ Trash ]   [ Analyze ]   [ Sandbox ]", True, (0, 0, 0))
                    tools_text = font.render("[ Trash ]   [ Analyze ]   [ Sandbox ]", True, (255, 255, 255))
                    t_x = card_rect.right - tools_text.get_width() - 8
                    t_y = card_rect.bottom - tools_text.get_height() - 8
                    screen.blit(tools_text_s, (t_x+2, t_y+2))
                    screen.blit(tools_text, (t_x, t_y))

                current_y += img_h + card_margin
                
            elif card.card_type in ["CODE", "TEXT"]:
                target_font = mono_font if card.card_type == "CODE" else font
                lines = []
                
                if card.label == "Syntax Detection":
                    lines.append("[ SYNTAX DETECTION ]")
                    lines.append("-" * 30)
                
                for paragraph in card.content.split('\n')[:80]:
                    words = paragraph.split(' ')
                    current_line = ""
                    for w in words:
                        if target_font.size(current_line + w)[0] < (wing_w - 4*card_margin):
                            current_line += w + " "
                        else:
                            if current_line: lines.append(current_line)
                            current_line = w + " "
                    if current_line: lines.append(current_line)
                
                block_h = len(lines) * target_font.get_linesize() + 2*card_margin
                pygame.draw.rect(screen, (20, 25, 30), (wing_x + card_margin, current_y, wing_w - 2*card_margin, block_h), border_radius=8)
                
                for i, line in enumerate(lines):
                    txt_surf = target_font.render(line, True, (200, 200, 200))
                    screen.blit(txt_surf, (wing_x + 2*card_margin, current_y + card_margin + i*target_font.get_linesize()))
                
                card_rect = pygame.Rect(wing_x + card_margin, current_y, wing_w - 2*card_margin, block_h)
                if card_rect.collidepoint(pygame.mouse.get_pos()):
                    # Command Deck Hover Element
                    tools_text_s = font.render("[ Trash ]   [ Analyze ]   [ Sandbox ]", True, (0, 0, 0))
                    tools_text = font.render("[ Trash ]   [ Analyze ]   [ Sandbox ]", True, (255, 255, 255))
                    t_x = card_rect.right - tools_text.get_width() - 8
                    t_y = card_rect.bottom - tools_text.get_height() - 8
                    screen.blit(tools_text_s, (t_x+2, t_y+2))
                    screen.blit(tools_text, (t_x, t_y))
                    
                current_y += block_h + card_margin
        
        # Constrain scrolling
        content_height = current_y - int(self.y_scroll) - card_margin
        max_scroll = min(0, -(content_height - self.height + card_margin))
        if self.y_scroll > 0: self.y_scroll *= 0.9
        elif self.y_scroll < max_scroll:
            self.y_scroll += (max_scroll - self.y_scroll) * 0.1
            
        # Neural Scan Line
        if self.wing_open_ratio > 0.5:
            import time
            scan_y = (math.sin(time.time() * 3) + 1.0) / 2.0
            scan_y_abs = int(scan_y * self.height)
            scan_color = (0, 212, 255)
            
            # Sub-surface blending for additive scanline
            scan_surf = pygame.Surface((wing_w, 3), pygame.SRCALPHA)
            scan_surf.fill((0, 212, 255, 150))
            screen.blit(scan_surf, (wing_x, scan_y_abs - 1), special_flags=pygame.BLEND_RGBA_ADD)
        
        screen.set_clip(old_clip)

    # ---- Subtitles ---------------------------------------------------------

    def render_subtitles(self, text, user_text, screen, font, fg_color, alpha):
        """Render the current subtitle text with a shadow at the bottom."""
        if not text and not user_text:
            return

        def wrap_text(t):
            max_px = int(self.width * 0.9)
            words = t.split()
            lines = []
            current = ""
            for w in words:
                trial = (current + " " + w).strip() if current else w
                if font.size(trial)[0] <= max_px:
                    current = trial
                else:
                    if current:
                        lines.append(current)
                    current = w
            if current:
                lines.append(current)
            return lines

        line_h = font.get_linesize()
        padding_y = 8
        bottom_margin = 24
        
        friday_lines = wrap_text(text) if text else []
        user_lines = wrap_text(user_text) if user_text else []
        
        total_lines = len(friday_lines) + len(user_lines)
        if friday_lines and user_lines:
            total_lines += 1  # Gap between user and Friday text
            
        block_height = line_h * total_lines + padding_y * 2
        rect_y = self.height - bottom_margin - block_height

        def draw_lines(lines, y_start, color):
            for i, line in enumerate(lines):
                shadow_surf = font.render(line, True, (0, 0, 0))
                fg_surf = font.render(line, True, color)
                shadow_surf.set_alpha(alpha)
                fg_surf.set_alpha(alpha)
                
                line_x = (self.width - fg_surf.get_width()) // 2
                line_y = y_start + i * line_h
                screen.blit(shadow_surf, (line_x + 2, line_y + 2))
                screen.blit(fg_surf, (line_x, line_y))

        current_y = rect_y + padding_y
        
        if user_lines:
            draw_lines(user_lines, current_y, (0, 212, 255))
            current_y += line_h * len(user_lines)
            if friday_lines:
                current_y += line_h

        if friday_lines:
            draw_lines(friday_lines, current_y, fg_color)
