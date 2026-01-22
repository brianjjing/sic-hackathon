#!/usr/bin/env python3
"""
Self-Driving Scooter Fleet Simulation
A pygame-based simulation of autonomous electric scooters that self-reposition to serve users.
"""

import pygame
import math
import random
from collections import namedtuple
from enum import Enum

# Initialize pygame
pygame.init()

# Constants
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800
FPS = 60

# Colors
COLOR_BACKGROUND = (128, 128, 128)  # Gray
COLOR_SCOOTER_BLUE = (50, 100, 255)
COLOR_SCOOTER_ORANGE = (255, 165, 0)
COLOR_SCOOTER_RED = (255, 50, 50)
COLOR_USER = (255, 0, 0)
COLOR_CHARGE_STATION = (0, 200, 0)
COLOR_OBSTACLE = (100, 100, 100)
COLOR_TEXT = (255, 255, 255)
COLOR_DEAD = (50, 50, 50)

# Game constants
SCOOTER_RADIUS = 12
USER_RADIUS = 10
CHARGE_STATION_SIZE = 40
OBSTACLE_MIN_SIZE = 20
OBSTACLE_MAX_SIZE = 50
NUM_SCOOTERS = 5
NUM_OBSTACLES = 8
NUM_CHARGE_STATIONS = 3

# Scooter constants
MAX_SPEED = 4.0
BATTERY_DRAIN_RATE = 0.05  # % per frame while moving
BATTERY_CHARGE_RATE = 0.5  # % per frame while charging
LOW_BATTERY_THRESHOLD = 20.0
PICKUP_DISTANCE = 15
OBSTACLE_AVOIDANCE_DISTANCE = 20
OBSTACLE_AVOIDANCE_ANGLE = math.radians(40)
STEERING_FACTOR = 0.1
MIN_RIDE_TIME = 600  # frames (10 seconds at 60 FPS)
MAX_RIDE_TIME = 1200  # frames (20 seconds at 60 FPS)

# Point namedtuple for 2D coordinates
Point = namedtuple('Point', ['x', 'y'])


class ScooterState(Enum):
    """Scooter state enumeration"""
    IDLE = "idle"
    TO_USER = "to_user"
    CARRYING = "carrying"
    RETURNING = "returning"
    CHARGING = "charging"
    DEAD = "dead"


class Obstacle:
    """Static obstacle on the map"""
    def __init__(self, x, y, width, height):
        self.rect = pygame.Rect(x, y, width, height)
    
    def contains_point(self, point, margin=0):
        """Check if point is within obstacle (with optional margin)"""
        expanded = self.rect.inflate(margin * 2, margin * 2)
        return expanded.collidepoint(point.x, point.y)
    
    def distance_to_point(self, point):
        """Calculate minimum distance from point to obstacle"""
        closest_x = max(self.rect.left, min(point.x, self.rect.right))
        closest_y = max(self.rect.top, min(point.y, self.rect.bottom))
        dx = point.x - closest_x
        dy = point.y - closest_y
        return math.sqrt(dx * dx + dy * dy)


class ChargeStation:
    """Charging station for scooters"""
    def __init__(self, x, y):
        self.pos = Point(x, y)
        self.rect = pygame.Rect(x - CHARGE_STATION_SIZE // 2, 
                               y - CHARGE_STATION_SIZE // 2,
                               CHARGE_STATION_SIZE, CHARGE_STATION_SIZE)
    
    def distance_to(self, point):
        """Calculate distance to a point"""
        dx = point.x - self.pos.x
        dy = point.y - self.pos.y
        return math.sqrt(dx * dx + dy * dy)
    
    def contains_point(self, point, margin=0):
        """Check if point is within station (with optional margin)"""
        expanded = self.rect.inflate(margin * 2, margin * 2)
        return expanded.collidepoint(point.x, point.y)


class User:
    """User request entity"""
    def __init__(self, x, y):
        self.pos = Point(x, y)
        self.pulse_phase = 0.0
        self.assigned_scooter = None
    
    def update(self):
        """Update user animation"""
        self.pulse_phase += 0.1
    
    def distance_to(self, point):
        """Calculate distance to a point"""
        dx = point.x - self.pos.x
        dy = point.y - self.pos.y
        return math.sqrt(dx * dx + dy * dy)


class Scooter:
    """Main scooter entity with state machine"""
    def __init__(self, x, y):
        self.pos = Point(x, y)
        self.velocity = 0.0
        self.angle = random.uniform(0, 2 * math.pi)
        self.target = None
        self.state = ScooterState.IDLE
        self.battery = 100.0
        self.carrying_user = None
        self.ride_timer = 0
        self.target_station = None
    
    def distance_to(self, point):
        """Calculate distance to a point"""
        dx = point.x - self.pos.x
        dy = point.y - self.pos.y
        return math.sqrt(dx * dx + dy * dy)
    
    def update(self, users, charge_stations, obstacles, scooters):
        """Update scooter state and position"""
        # Check for battery death
        if self.battery <= 0:
            self.state = ScooterState.DEAD
            self.velocity = 0.0
            return
        
        # Force return if low battery (unless already charging or dead)
        if self.battery < LOW_BATTERY_THRESHOLD and self.state not in [ScooterState.CHARGING, ScooterState.DEAD, ScooterState.RETURNING]:
            self.state = ScooterState.RETURNING
            self.target = None
            self.carrying_user = None
        
        # State machine logic
        if self.state == ScooterState.IDLE:
            self._update_idle()
        elif self.state == ScooterState.TO_USER:
            self._update_to_user(obstacles, scooters)
        elif self.state == ScooterState.CARRYING:
            self._update_carrying(obstacles, scooters)
        elif self.state == ScooterState.RETURNING:
            self._update_returning(charge_stations, obstacles, scooters)
        elif self.state == ScooterState.CHARGING:
            self._update_charging()
        
        # Update position based on velocity
        if self.velocity > 0 and self.state != ScooterState.DEAD:
            dx = math.cos(self.angle) * self.velocity
            dy = math.sin(self.angle) * self.velocity
            new_x = self.pos.x + dx
            new_y = self.pos.y + dy
            
            # Keep within bounds
            new_x = max(SCOOTER_RADIUS, min(WINDOW_WIDTH - SCOOTER_RADIUS, new_x))
            new_y = max(SCOOTER_RADIUS, min(WINDOW_HEIGHT - SCOOTER_RADIUS, new_y))
            
            self.pos = Point(new_x, new_y)
            
            # Drain battery while moving
            self.battery = max(0, self.battery - BATTERY_DRAIN_RATE)
    
    def _update_idle(self):
        """Idle state: slight random wander"""
        if random.random() < 0.02:  # Occasionally change direction
            self.angle += random.uniform(-0.5, 0.5)
        self.velocity = random.uniform(0.5, 1.5)
    
    def _update_to_user(self, obstacles, scooters):
        """Move toward target user"""
        if self.target is None:
            self.state = ScooterState.IDLE
            return
        
        # Calculate desired angle to target
        dx = self.target.x - self.pos.x
        dy = self.target.y - self.pos.y
        distance = math.sqrt(dx * dx + dy * dy)
        
        if distance < PICKUP_DISTANCE:
            # Reached user - switch to carrying
            self.state = ScooterState.CARRYING
            self.carrying_user = self.target
            self.target = None
            self.ride_timer = random.randint(MIN_RIDE_TIME, MAX_RIDE_TIME)
            return
        
        desired_angle = math.atan2(dy, dx)
        
        # Steer toward target
        angle_diff = desired_angle - self.angle
        # Normalize angle difference to [-pi, pi]
        while angle_diff > math.pi:
            angle_diff -= 2 * math.pi
        while angle_diff < -math.pi:
            angle_diff += 2 * math.pi
        
        self.angle += angle_diff * STEERING_FACTOR
        
        # Obstacle avoidance
        self._avoid_obstacles(obstacles, scooters)
        
        # Set velocity
        self.velocity = min(MAX_SPEED, distance * 0.1)
    
    def _update_carrying(self, obstacles, scooters):
        """Carrying state: simulate ride"""
        self.ride_timer -= 1
        
        if self.ride_timer <= 0:
            # Drop off user
            if self.carrying_user:
                self.carrying_user = None
            self.state = ScooterState.RETURNING
            self.target = None
            return
        
        # Random movement during ride
        if random.random() < 0.05:
            self.angle += random.uniform(-0.3, 0.3)
        
        # Obstacle avoidance
        self._avoid_obstacles(obstacles, scooters)
        
        self.velocity = random.uniform(2.0, MAX_SPEED)
    
    def _update_returning(self, charge_stations, obstacles, scooters):
        """Return to nearest charge station"""
        # Find nearest station if not already targeted
        if self.target_station is None or not self.target_station.contains_point(self.pos, margin=5):
            min_dist = float('inf')
            nearest = None
            for station in charge_stations:
                dist = station.distance_to(self.pos)
                if dist < min_dist:
                    min_dist = dist
                    nearest = station
            self.target_station = nearest
        
        if self.target_station is None:
            return
        
        # Check if reached station
        if self.target_station.contains_point(self.pos, margin=CHARGE_STATION_SIZE // 2):
            self.state = ScooterState.CHARGING
            self.velocity = 0.0
            return
        
        # Move toward station
        dx = self.target_station.pos.x - self.pos.x
        dy = self.target_station.pos.y - self.pos.y
        desired_angle = math.atan2(dy, dx)
        
        angle_diff = desired_angle - self.angle
        while angle_diff > math.pi:
            angle_diff -= 2 * math.pi
        while angle_diff < -math.pi:
            angle_diff += 2 * math.pi
        
        self.angle += angle_diff * STEERING_FACTOR
        
        # Obstacle avoidance
        self._avoid_obstacles(obstacles, scooters)
        
        distance = self.target_station.distance_to(self.pos)
        self.velocity = min(MAX_SPEED, distance * 0.1)
    
    def _update_charging(self):
        """Charging state: recharge battery"""
        self.velocity = 0.0
        self.battery = min(100.0, self.battery + BATTERY_CHARGE_RATE)
        
        if self.battery >= 100.0:
            self.state = ScooterState.IDLE
            self.target_station = None
    
    def _avoid_obstacles(self, obstacles, scooters):
        """Steer away from nearby obstacles and other scooters"""
        avoidance_angle = 0.0
        avoidance_count = 0
        
        # Check obstacles
        for obstacle in obstacles:
            dist = obstacle.distance_to_point(self.pos)
            if dist < OBSTACLE_AVOIDANCE_DISTANCE:
                # Calculate angle away from obstacle
                dx = self.pos.x - (obstacle.rect.centerx)
                dy = self.pos.y - (obstacle.rect.centery)
                avoid_angle = math.atan2(dy, dx)
                avoidance_angle += avoid_angle
                avoidance_count += 1
        
        # Check other scooters
        for scooter in scooters:
            if scooter is self or scooter.state == ScooterState.DEAD:
                continue
            dx = self.pos.x - scooter.pos.x
            dy = self.pos.y - scooter.pos.y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < OBSTACLE_AVOIDANCE_DISTANCE and dist > 0:
                avoid_angle = math.atan2(dy, dx)
                avoidance_angle += avoid_angle
                avoidance_count += 1
        
        # Apply avoidance
        if avoidance_count > 0:
            avoidance_angle /= avoidance_count
            angle_diff = avoidance_angle - self.angle
            while angle_diff > math.pi:
                angle_diff -= 2 * math.pi
            while angle_diff < -math.pi:
                angle_diff += 2 * math.pi
            self.angle += angle_diff * OBSTACLE_AVOIDANCE_ANGLE / math.pi
    
    def assign_user(self, user):
        """Assign a user to this scooter"""
        self.target = user.pos
        self.state = ScooterState.TO_USER
        user.assigned_scooter = self
    
    def get_color(self):
        """Get color based on battery level"""
        if self.state == ScooterState.DEAD:
            return COLOR_DEAD
        elif self.battery < LOW_BATTERY_THRESHOLD:
            return COLOR_SCOOTER_RED
        elif self.battery < 50:
            return COLOR_SCOOTER_ORANGE
        else:
            return COLOR_SCOOTER_BLUE
    
    def get_state_label(self):
        """Get state label for display"""
        labels = {
            ScooterState.IDLE: "I",
            ScooterState.TO_USER: "U",
            ScooterState.CARRYING: "C",
            ScooterState.RETURNING: "R",
            ScooterState.CHARGING: "⚡",
            ScooterState.DEAD: "X"
        }
        return labels.get(self.state, "?")


class Simulation:
    """Main simulation class"""
    def __init__(self):
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Self-Driving Scooter Fleet Simulation")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 24)
        self.small_font = pygame.font.Font(None, 18)
        
        # Initialize game objects
        self.scooters = []
        self.users = []
        self.charge_stations = []
        self.obstacles = []
        
        self._initialize_map()
        self._initialize_scooters()
        
        # View mode
        self.view_mode = "aerial"  # "aerial" or "first_person"
        self.fp_scooter_index = 0
    
    def _initialize_map(self):
        """Initialize map with obstacles and charge stations"""
        # Create obstacles
        for _ in range(NUM_OBSTACLES):
            width = random.randint(OBSTACLE_MIN_SIZE, OBSTACLE_MAX_SIZE)
            height = random.randint(OBSTACLE_MIN_SIZE, OBSTACLE_MAX_SIZE)
            x = random.randint(50, WINDOW_WIDTH - 50)
            y = random.randint(50, WINDOW_HEIGHT - 50)
            self.obstacles.append(Obstacle(x, y, width, height))
        
        # Create charge stations at corners
        margin = 60
        positions = [
            (margin, margin),
            (WINDOW_WIDTH - margin, margin),
            (WINDOW_WIDTH - margin, WINDOW_HEIGHT - margin),
            (margin, WINDOW_HEIGHT - margin)
        ]
        for i, (x, y) in enumerate(positions[:NUM_CHARGE_STATIONS]):
            self.charge_stations.append(ChargeStation(x, y))
    
    def _initialize_scooters(self):
        """Initialize scooters at random positions"""
        for _ in range(NUM_SCOOTERS):
            x = random.randint(SCOOTER_RADIUS * 2, WINDOW_WIDTH - SCOOTER_RADIUS * 2)
            y = random.randint(SCOOTER_RADIUS * 2, WINDOW_HEIGHT - SCOOTER_RADIUS * 2)
            self.scooters.append(Scooter(x, y))
    
    def handle_events(self):
        """Handle pygame events"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # Left click
                    x, y = event.pos
                    # Spawn user
                    user = User(x, y)
                    self.users.append(user)
                    # Auto-assign to closest idle scooter
                    self._assign_user_to_scooter(user)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_1:
                    # Toggle first-person view
                    if self.view_mode == "aerial":
                        self.view_mode = "first_person"
                        self.fp_scooter_index = 0
                elif event.key == pygame.K_a:
                    # Return to aerial view
                    self.view_mode = "aerial"
        
        # Handle continuous key presses for first-person manual controls
        if self.view_mode == "first_person" and self.scooters:
            keys = pygame.key.get_pressed()
            scooter = self.scooters[self.fp_scooter_index]
            manual_override = False
            
            if keys[pygame.K_UP]:
                scooter.velocity = min(MAX_SPEED, scooter.velocity + 0.2)
                manual_override = True
            if keys[pygame.K_DOWN]:
                scooter.velocity = max(0, scooter.velocity - 0.2)
                manual_override = True
            if keys[pygame.K_LEFT]:
                scooter.angle -= 0.05
                manual_override = True
            if keys[pygame.K_RIGHT]:
                scooter.angle += 0.05
                manual_override = True
            
            # Update position if manually controlled
            if manual_override and scooter.velocity > 0:
                dx = math.cos(scooter.angle) * scooter.velocity
                dy = math.sin(scooter.angle) * scooter.velocity
                new_x = scooter.pos.x + dx
                new_y = scooter.pos.y + dy
                new_x = max(SCOOTER_RADIUS, min(WINDOW_WIDTH - SCOOTER_RADIUS, new_x))
                new_y = max(SCOOTER_RADIUS, min(WINDOW_HEIGHT - SCOOTER_RADIUS, new_y))
                scooter.pos = Point(new_x, new_y)
                scooter.battery = max(0, scooter.battery - BATTERY_DRAIN_RATE)
        
        return True
    
    def _assign_user_to_scooter(self, user):
        """Assign user to closest idle scooter"""
        min_dist = float('inf')
        closest_scooter = None
        
        for scooter in self.scooters:
            if scooter.state == ScooterState.IDLE and scooter.battery > 0:
                dist = scooter.distance_to(user.pos)
                if dist < min_dist:
                    min_dist = dist
                    closest_scooter = scooter
        
        if closest_scooter:
            closest_scooter.assign_user(user)
        # If no idle scooter, user will wait (shown in queue)
    
    def update(self):
        """Update all game objects"""
        # Update scooters
        for scooter in self.scooters:
            scooter.update(self.users, self.charge_stations, self.obstacles, self.scooters)
        
        # Update users
        for user in self.users[:]:
            user.update()
            # Remove users that have been picked up
            if user.assigned_scooter and user.assigned_scooter.carrying_user != user:
                if user in self.users:
                    self.users.remove(user)
        
        # Check for unassigned users and try to assign them
        for user in self.users:
            if user.assigned_scooter is None:
                self._assign_user_to_scooter(user)
    
    def draw_aerial_view(self):
        """Draw aerial top-down view"""
        # Background
        self.screen.fill(COLOR_BACKGROUND)
        
        # Draw obstacles
        for obstacle in self.obstacles:
            pygame.draw.rect(self.screen, COLOR_OBSTACLE, obstacle.rect)
        
        # Draw charge stations
        for station in self.charge_stations:
            pygame.draw.rect(self.screen, COLOR_CHARGE_STATION, station.rect)
            text = self.small_font.render("CHARGE", True, COLOR_TEXT)
            text_rect = text.get_rect(center=(station.pos.x, station.pos.y))
            self.screen.blit(text, text_rect)
        
        # Draw users
        for user in self.users:
            # Pulsing effect
            pulse = abs(math.sin(user.pulse_phase)) * 0.3 + 0.7
            radius = int(USER_RADIUS * pulse)
            pygame.draw.circle(self.screen, COLOR_USER, (int(user.pos.x), int(user.pos.y)), radius)
            # Waiting indicator if not assigned
            if user.assigned_scooter is None:
                text = self.small_font.render("?", True, COLOR_TEXT)
                text_rect = text.get_rect(center=(int(user.pos.x), int(user.pos.y)))
                self.screen.blit(text, text_rect)
        
        # Draw scooters
        for scooter in self.scooters:
            color = scooter.get_color()
            # Draw scooter circle
            pygame.draw.circle(self.screen, color, (int(scooter.pos.x), int(scooter.pos.y)), SCOOTER_RADIUS)
            # Draw direction arrow
            arrow_length = SCOOTER_RADIUS + 5
            end_x = scooter.pos.x + math.cos(scooter.angle) * arrow_length
            end_y = scooter.pos.y + math.sin(scooter.angle) * arrow_length
            pygame.draw.line(self.screen, COLOR_TEXT, 
                           (int(scooter.pos.x), int(scooter.pos.y)),
                           (int(end_x), int(end_y)), 2)
            # Draw state label
            label = scooter.get_state_label()
            text = self.small_font.render(label, True, COLOR_TEXT)
            text_rect = text.get_rect(center=(int(scooter.pos.x), int(scooter.pos.y)))
            self.screen.blit(text, text_rect)
        
        # Draw HUD
        self._draw_hud()
    
    def _draw_hud(self):
        """Draw HUD overlay with fleet stats"""
        # Calculate stats
        idle_count = sum(1 for s in self.scooters if s.state == ScooterState.IDLE)
        idle_percent = (idle_count / len(self.scooters)) * 100 if self.scooters else 0
        avg_battery = sum(s.battery for s in self.scooters) / len(self.scooters) if self.scooters else 0
        active_users = len(self.users)
        
        # Draw HUD background
        hud_rect = pygame.Rect(10, 10, 250, 100)
        pygame.draw.rect(self.screen, (0, 0, 0, 180), hud_rect)
        pygame.draw.rect(self.screen, (255, 255, 255), hud_rect, 2)
        
        # Draw stats
        y_offset = 20
        stats = [
            f"Idle: {idle_percent:.1f}% ({idle_count}/{len(self.scooters)})",
            f"Avg Battery: {avg_battery:.1f}%",
            f"Active Users: {active_users}",
            f"Click to summon user"
        ]
        
        for stat in stats:
            text = self.small_font.render(stat, True, COLOR_TEXT)
            self.screen.blit(text, (20, y_offset))
            y_offset += 20
    
    def draw_first_person_view(self):
        """Draw first-person view from scooter perspective"""
        if not self.scooters or self.fp_scooter_index >= len(self.scooters):
            self.view_mode = "aerial"
            return
        
        scooter = self.scooters[self.fp_scooter_index]
        
        # Background (sky)
        self.screen.fill((135, 206, 235))
        
        # Draw fake 3D ground
        center_x = WINDOW_WIDTH // 2
        center_y = WINDOW_HEIGHT // 2
        
        # Ground color
        pygame.draw.rect(self.screen, (200, 200, 200), 
                        (0, center_y, WINDOW_WIDTH, WINDOW_HEIGHT - center_y))
        
        # Perspective grid lines
        for i in range(10):
            y = center_y + i * 30
            width = WINDOW_WIDTH * (1 - i * 0.05)
            if width > 0:
                x = (WINDOW_WIDTH - width) // 2
                pygame.draw.line(self.screen, (150, 150, 150), 
                               (x, y), (x + width, y), 1)
        
        # Draw obstacles in perspective
        for obstacle in self.obstacles:
            # Calculate relative position
            dx = obstacle.rect.centerx - scooter.pos.x
            dy = obstacle.rect.centery - scooter.pos.y
            
            # Rotate to scooter's perspective
            angle_to_obstacle = math.atan2(dy, dx) - scooter.angle
            distance = math.sqrt(dx * dx + dy * dy)
            
            if distance < 300 and abs(angle_to_obstacle) < math.pi / 2:
                # Project to screen
                screen_x = center_x + math.sin(angle_to_obstacle) * 200
                screen_y = center_y - distance * 0.3
                size = max(10, 100 - distance * 0.2)
                
                if screen_y < center_y:
                    pygame.draw.rect(self.screen, COLOR_OBSTACLE,
                                   (screen_x - size // 2, screen_y - size, size, size))
        
        # Draw target direction arrow if scooter has a target
        if scooter.target:
            dx = scooter.target.x - scooter.pos.x
            dy = scooter.target.y - scooter.pos.y
            target_angle = math.atan2(dy, dx) - scooter.angle
            
            # Normalize angle
            while target_angle > math.pi:
                target_angle -= 2 * math.pi
            while target_angle < -math.pi:
                target_angle += 2 * math.pi
            
            # Draw arrow on screen (centered, pointing to target)
            arrow_x = center_x + math.sin(target_angle) * 150
            arrow_y = center_y - 50
            
            # Draw arrow line
            pygame.draw.line(self.screen, (255, 255, 0), 
                           (center_x, center_y - 20), (int(arrow_x), int(arrow_y)), 3)
            # Draw arrowhead
            arrow_size = 10
            arrow_angle1 = target_angle + math.pi - 0.5
            arrow_angle2 = target_angle + math.pi + 0.5
            pygame.draw.line(self.screen, (255, 255, 0),
                           (int(arrow_x), int(arrow_y)),
                           (int(arrow_x + math.cos(arrow_angle1) * arrow_size),
                            int(arrow_y + math.sin(arrow_angle1) * arrow_size)), 3)
            pygame.draw.line(self.screen, (255, 255, 0),
                           (int(arrow_x), int(arrow_y)),
                           (int(arrow_x + math.cos(arrow_angle2) * arrow_size),
                            int(arrow_y + math.sin(arrow_angle2) * arrow_size)), 3)
        
        # Draw HUD overlay
        hud_rect = pygame.Rect(10, 10, 200, 120)
        pygame.draw.rect(self.screen, (0, 0, 0, 180), hud_rect)
        pygame.draw.rect(self.screen, (255, 255, 255), hud_rect, 2)
        
        y_offset = 20
        info = [
            f"Speed: {scooter.velocity:.1f}",
            f"Battery: {scooter.battery:.1f}%",
            f"State: {scooter.state.value}",
            f"Angle: {math.degrees(scooter.angle):.1f}°",
            "",
            "Press 'A' for aerial"
        ]
        
        for line in info:
            text = self.small_font.render(line, True, COLOR_TEXT)
            self.screen.blit(text, (20, y_offset))
            y_offset += 18
    
    def draw(self):
        """Draw current view"""
        if self.view_mode == "aerial":
            self.draw_aerial_view()
        else:
            self.draw_first_person_view()
    
    def run(self):
        """Main game loop"""
        running = True
        while running:
            running = self.handle_events()
            self.update()
            self.draw()
            pygame.display.flip()
            self.clock.tick(FPS)
        
        pygame.quit()


def main():
    """Entry point"""
    sim = Simulation()
    sim.run()


if __name__ == "__main__":
    main()