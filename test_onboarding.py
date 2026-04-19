"""Test Zara Onboarding UI standalone."""

import pygame
import sys
from onboarding_ui import OnboardingUI, UserProfile

# Initialize Pygame
pygame.init()
pygame.font.init()

# Set up display
screen = pygame.display.set_mode((800, 600), pygame.RESIZABLE)
pygame.display.set_caption("Zara Onboarding Preview")
clock = pygame.time.Clock()

# Create onboarding UI
onboarding = OnboardingUI(800, 600)
onboarding_complete = False

def on_complete():
    global onboarding_complete
    onboarding_complete = True
    print("✅ Onboarding complete!")
    print(f"Profile: {onboarding.profile.__dict__}")

onboarding.on_complete = on_complete

# Main loop
running = True
while running and not onboarding_complete:
    dt = clock.tick(60) / 1000.0
    
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.VIDEORESIZE:
            screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
            onboarding.width = event.w
            onboarding.height = event.h
        
        # Let onboarding handle its events
        onboarding.handle_event(event)
    
    # Update animations
    onboarding.update(dt)
    
    # Clear screen with dark background
    screen.fill((10, 12, 16))
    
    # Render onboarding overlay
    onboarding.render(screen)
    
    pygame.display.flip()

pygame.quit()
sys.exit()
