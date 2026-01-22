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
COLOR_BACKGROUND = (50, 150, 50)  # Green
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
OBSTACLE_MIN_SIZE = 40
OBSTACLE_MAX_SIZE = 120
NUM_SCOOTERS = 10
NUM_OBSTACLES = 18
NUM_CHARGE_STATIONS = 3
NUM_SPIN_SCOOTERS = 10

# Pedestrian constants
TARGET_PEDESTRIANS_OUR = 3  # Pedestrians using our scooters
TARGET_PEDESTRIANS_SPIN = 3  # Pedestrians using SPIN
TARGET_TOTAL_PEDESTRIANS = TARGET_PEDESTRIANS_OUR + TARGET_PEDESTRIANS_SPIN
PEDESTRIAN_SPAWN_INTERVAL = 60  # Spawn every 60 frames (1 second at 60 FPS)

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

# Collision avoidance constants
COLLISION_AVOIDANCE_DISTANCE = 30  # For scooters
SEPARATION_FORCE_MULTIPLIER = 2.0

# SPIN competitor constants
SPIN_COLOR = (255, 100, 0)  # Orange
PEDESTRIAN_SPEED = 0.375  # px/frame (1.5 / 4 = 0.375, much slower than scooters)
PEDESTRIAN_RADIUS = 6

# Landmark constants
LANDMARK_SIZE = 35
LANDMARK_COLORS = {
    "Library": (50, 100, 255),      # Blue
    "Restaurant": (255, 165, 0),   # Orange
    "Church": (200, 100, 255),     # Purple
    "Park": (50, 200, 50),         # Green
    "School": (255, 255, 0),        # Yellow
    "Hospital": (255, 50, 50),     # Red
}
LANDMARK_NAMES = list(LANDMARK_COLORS.keys())

# Point namedtuple for 2D coordinates
Point = namedtuple('Point', ['x', 'y'])


class ScooterState(Enum):
    """Scooter state enumeration"""
    IDLE = "idle"
    TO_USER = "to_user"
    TO_DESTINATION = "to_destination"
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


class Landmark:
    """Programmed place on the map (library, restaurant, etc.)"""
    def __init__(self, name, x, y):
        self.name = name
        self.pos = Point(x, y)
        self.color = LANDMARK_COLORS.get(name, (150, 150, 150))
        self.rect = pygame.Rect(x - LANDMARK_SIZE // 2, 
                               y - LANDMARK_SIZE // 2,
                               LANDMARK_SIZE, LANDMARK_SIZE)
    
    def distance_to(self, point):
        """Calculate distance to a point"""
        dx = point.x - self.pos.x
        dy = point.y - self.pos.y
        return math.sqrt(dx * dx + dy * dy)
    
    def contains_point(self, point, margin=0):
        """Check if point is within landmark (with optional margin)"""
        expanded = self.rect.inflate(margin * 2, margin * 2)
        return expanded.collidepoint(point.x, point.y)


class User:
    """User request entity"""
    def __init__(self, origin_x, origin_y, destination=None):
        self.origin = Point(origin_x, origin_y)
        self.pos = self.origin  # Current position (starts at origin)
        self.destination = destination  # Point or Landmark
        self.pulse_phase = 0.0
        self.assigned_scooter = None
        self.state = "waiting"  # "waiting", "picked_up", "completed"
    
    def update(self):
        """Update user animation"""
        self.pulse_phase += 0.1
    
    def distance_to(self, point):
        """Calculate distance to a point"""
        dx = point.x - self.pos.x
        dy = point.y - self.pos.y
        return math.sqrt(dx * dx + dy * dy)
    
    def get_destination_point(self):
        """Get destination as Point (if Landmark, return its position)"""
        if isinstance(self.destination, Landmark):
            return self.destination.pos
        return self.destination


class Scooter:
    """Main scooter entity with state machine"""
    def __init__(self, x, y):
        self.pos = Point(x, y)
        self.velocity = 0.0
        self.angle = random.uniform(0, 2 * math.pi)
        self.target = None
        self.destination = None  # Final destination for current ride
        self.state = ScooterState.IDLE
        self.battery = 100.0
        self.carrying_user = None
        self.ride_timer = 0
        self.target_station = None
        self.origin_dock = None  # Dock where scooter started from
    
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
        elif self.state == ScooterState.TO_DESTINATION:
            self._update_to_destination(obstacles, scooters)
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
        """Idle state: stay at dock or slight random wander"""
        # If at a dock, stay put
        if self.target_station and self.target_station.contains_point(self.pos, margin=CHARGE_STATION_SIZE // 2):
            self.velocity = 0.0
        else:
            # Not at dock - slight random wander
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
            # Reached user - switch to TO_DESTINATION
            if self.carrying_user and self.carrying_user.destination:
                self.carrying_user.state = "picked_up"
                self.destination = self.carrying_user.get_destination_point()
                self.target = self.destination
                self.state = ScooterState.TO_DESTINATION
            else:
                # Fallback to old behavior (no destination set)
                self.state = ScooterState.CARRYING
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
    
    def _update_to_destination(self, obstacles, scooters):
        """Navigate to user's destination"""
        if self.target is None or self.destination is None:
            # No destination - fallback to returning
            self.state = ScooterState.RETURNING
            if self.carrying_user:
                self.carrying_user.state = "completed"
                self.carrying_user = None
            return
        
        # Calculate desired angle to destination
        dx = self.target.x - self.pos.x
        dy = self.target.y - self.pos.y
        distance = math.sqrt(dx * dx + dy * dy)
        
        if distance < PICKUP_DISTANCE:
            # Reached destination - drop off user
            if self.carrying_user:
                self.carrying_user.state = "completed"
                self.carrying_user = None
            self.destination = None
            self.target = None
            self.state = ScooterState.RETURNING
            return
        
        desired_angle = math.atan2(dy, dx)
        
        # Steer toward destination
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
    
    def _predict_collision(self, other_scooter, lookahead_frames=5):
        """Predict if collision will occur in next few frames"""
        # Calculate future positions
        my_future_x = self.pos.x + math.cos(self.angle) * self.velocity * lookahead_frames
        my_future_y = self.pos.y + math.sin(self.angle) * self.velocity * lookahead_frames
        other_future_x = other_scooter.pos.x + math.cos(other_scooter.angle) * other_scooter.velocity * lookahead_frames
        other_future_y = other_scooter.pos.y + math.sin(other_scooter.angle) * other_scooter.velocity * lookahead_frames
        
        future_dist = math.sqrt((my_future_x - other_future_x)**2 + (my_future_y - other_future_y)**2)
        return future_dist < (SCOOTER_RADIUS * 2 + 10)
    
    def _avoid_obstacles(self, obstacles, scooters):
        """Enhanced obstacle and scooter avoidance with separation forces and predictive collision"""
        separation_force_x = 0.0
        separation_force_y = 0.0
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
        
        # Enhanced scooter avoidance with separation forces
        for scooter in scooters:
            if scooter is self or scooter.state == ScooterState.DEAD:
                continue
            
            dx = self.pos.x - scooter.pos.x
            dy = self.pos.y - scooter.pos.y
            dist = math.sqrt(dx * dx + dy * dy)
            
            if dist < COLLISION_AVOIDANCE_DISTANCE and dist > 0:
                # Separation force (stronger when closer)
                force_strength = SEPARATION_FORCE_MULTIPLIER * (1.0 - dist / COLLISION_AVOIDANCE_DISTANCE)
                separation_force_x += (dx / dist) * force_strength
                separation_force_y += (dy / dist) * force_strength
                
                # Predictive collision check
                if self._predict_collision(scooter):
                    # Stronger avoidance if collision predicted
                    avoid_angle = math.atan2(dy, dx)
                    avoidance_angle += avoid_angle * 2.0
                    avoidance_count += 2
                else:
                    avoid_angle = math.atan2(dy, dx)
                    avoidance_angle += avoid_angle
                    avoidance_count += 1
                
                # Velocity matching (align with nearby scooters to reduce conflicts)
                if dist < COLLISION_AVOIDANCE_DISTANCE * 0.7:
                    # Slight velocity alignment
                    target_vel = scooter.velocity
                    self.velocity = self.velocity * 0.9 + target_vel * 0.1
        
        # Apply separation force
        if separation_force_x != 0 or separation_force_y != 0:
            separation_angle = math.atan2(separation_force_y, separation_force_x)
            angle_diff = separation_angle - self.angle
            while angle_diff > math.pi:
                angle_diff -= 2 * math.pi
            while angle_diff < -math.pi:
                angle_diff += 2 * math.pi
            # Strong separation adjustment
            self.angle += angle_diff * 0.3
        
        # Apply avoidance angle
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
        self.target = user.origin  # Target is user's origin (pickup location)
        self.carrying_user = user  # Store user object for later
        # Record origin dock when leaving IDLE state
        if self.state == ScooterState.IDLE and self.target_station:
            self.origin_dock = self.target_station
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
            ScooterState.TO_DESTINATION: "D",
            ScooterState.CARRYING: "C",
            ScooterState.RETURNING: "R",
            ScooterState.CHARGING: "⚡",
            ScooterState.DEAD: "X"
        }
        return labels.get(self.state, "?")


class SpinScooter:
    """SPIN competitor scooter - stationary, users must walk to it"""
    def __init__(self, x, y):
        self.pos = Point(x, y)
        self.available = True
        self.battery = 100.0
        self.user = None
        self.destination = None
        self.ride_timer = 0
        self.velocity = 0.0
        self.angle = 0.0
    
    def assign_user(self, user):
        """Assign a user to this SPIN scooter"""
        self.user = user
        self.available = False
        user.assigned_scooter = self
        user.state = "walking_to_spin"
    
    def update(self, obstacles):
        """Update SPIN scooter state"""
        if self.user is None:
            return
        
        # If user is walking to scooter, wait
        if self.user.state == "walking_to_spin":
            return
        
        # If user is riding, move to destination
        if self.user.state == "riding_spin":
            if self.destination is None:
                # Set destination
                self.destination = self.user.get_destination_point()
                self.ride_timer = random.randint(MIN_RIDE_TIME, MAX_RIDE_TIME)
            
            # Move toward destination
            if self.destination:
                dx = self.destination.x - self.pos.x
                dy = self.destination.y - self.pos.y
                distance = math.sqrt(dx * dx + dy * dy)
                
                if distance < PICKUP_DISTANCE:
                    # Reached destination
                    self.user.state = "completed"
                    self.user = None
                    self.destination = None
                    self.available = True
                    self.velocity = 0.0
                    return
                
                # Move toward destination
                self.angle = math.atan2(dy, dx)
                self.velocity = min(MAX_SPEED * 0.8, distance * 0.1)  # Slightly slower than our scooters
                
                # Update position
                new_x = self.pos.x + math.cos(self.angle) * self.velocity
                new_y = self.pos.y + math.sin(self.angle) * self.velocity
                new_x = max(SCOOTER_RADIUS, min(WINDOW_WIDTH - SCOOTER_RADIUS, new_x))
                new_y = max(SCOOTER_RADIUS, min(WINDOW_HEIGHT - SCOOTER_RADIUS, new_y))
                self.pos = Point(new_x, new_y)
                
                # Drain battery
                self.battery = max(0, self.battery - BATTERY_DRAIN_RATE)
    
    def distance_to(self, point):
        """Calculate distance to a point"""
        dx = point.x - self.pos.x
        dy = point.y - self.pos.y
        return math.sqrt(dx * dx + dy * dy)


class Pedestrian:
    """Person walking to/from SPIN scooter"""
    def __init__(self, x, y, target_scooter, user):
        self.pos = Point(x, y)
        self.target_scooter = target_scooter
        self.target = target_scooter.pos
        self.user = user
        self.speed = PEDESTRIAN_SPEED
        self.state = "walking_to_scooter"
    
    def update(self):
        """Update pedestrian position"""
        if self.state == "walking_to_scooter":
            # Walk toward scooter
            dx = self.target_scooter.pos.x - self.pos.x
            dy = self.target_scooter.pos.y - self.pos.y
            distance = math.sqrt(dx * dx + dy * dy)
            
            if distance < PICKUP_DISTANCE + 5:
                # Reached scooter - start riding
                self.state = "riding"
                self.user.state = "riding_spin"
                self.user.pos = self.target_scooter.pos
            else:
                # Move toward scooter
                angle = math.atan2(dy, dx)
                new_x = self.pos.x + math.cos(angle) * self.speed
                new_y = self.pos.y + math.sin(angle) * self.speed
                self.pos = Point(new_x, new_y)
        elif self.state == "riding":
            # Update position to match scooter
            self.pos = self.target_scooter.pos
            # Check if ride is complete
            if self.user.state == "completed":
                self.state = "walking_away"
        elif self.state == "walking_away":
            # Walk away from scooter (can despawn after a bit)
            dx = self.pos.x - self.target_scooter.pos.x
            dy = self.pos.y - self.target_scooter.pos.y
            if abs(dx) < 1 and abs(dy) < 1:
                dx = random.uniform(-1, 1)
                dy = random.uniform(-1, 1)
            angle = math.atan2(dy, dx)
            new_x = self.pos.x + math.cos(angle) * self.speed
            new_y = self.pos.y + math.sin(angle) * self.speed
            self.pos = Point(new_x, new_y)


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
        self.landmarks = []
        self.spin_scooters = []
        self.pedestrians = []
        
        self._initialize_map()
        self._initialize_landmarks()
        self._initialize_scooters()
        self._initialize_spin_scooters()
        
        # View mode
        self.view_mode = "aerial"  # "aerial" or "first_person"
        self.fp_scooter_index = 0
        
        # Two-click interaction state
        self.pending_user_origin = None
        
        # Slider for adding scooters
        self.slider_x = 300
        self.slider_y = 30
        self.slider_width = 200
        self.slider_height = 20
        self.slider_min = 10
        self.slider_max = 30
        self.slider_value = len(self.scooters)  # Initialize to current count
        self.slider_dragging = False
        
        # Comparison metrics
        self.our_rides_count = 0
        self.spin_rides_count = 0
        self.our_ride_times = []  # List of trip durations
        self.spin_ride_times = []  # List of trip durations
        self.our_active_users = 0
        self.spin_active_users = 0
        self.ride_start_times = {}  # Track when rides started (by user)
        
        # Auto-spawn pedestrians (rate limited to 1 per second)
        self.pedestrian_spawn_timer = 0
        
        # Auto-spawn pedestrians (rate limited)
        self.pedestrian_spawn_timer = 0
    
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
    
    def _initialize_landmarks(self):
        """Initialize landmarks on the map"""
        # Place landmarks at strategic locations
        landmark_positions = [
            ("Library", 200, 200),
            ("Restaurant", 800, 300),
            ("Church", 400, 600),
            ("Park", 1000, 500),
            ("School", 600, 150),
            ("Hospital", 300, 400),
        ]
        
        for name, x, y in landmark_positions:
            self.landmarks.append(Landmark(name, x, y))
    
    def _initialize_scooters(self):
        """Initialize scooters at random positions"""
        # Place all scooters randomly on the map
        for _ in range(NUM_SCOOTERS):
            x = random.randint(SCOOTER_RADIUS * 2, WINDOW_WIDTH - SCOOTER_RADIUS * 2)
            y = random.randint(SCOOTER_RADIUS * 2, WINDOW_HEIGHT - SCOOTER_RADIUS * 2)
            self.scooters.append(Scooter(x, y))
    
    def _initialize_spin_scooters(self):
        """Initialize SPIN competitor scooters at random positions"""
        for _ in range(NUM_SPIN_SCOOTERS):
            x = random.randint(SCOOTER_RADIUS * 2, WINDOW_WIDTH - SCOOTER_RADIUS * 2)
            y = random.randint(SCOOTER_RADIUS * 2, WINDOW_HEIGHT - SCOOTER_RADIUS * 2)
            self.spin_scooters.append(SpinScooter(x, y))
    
    def _add_scooter(self):
        """Dynamically add a new scooter at random position"""
        # Place randomly on the map
        x = random.randint(SCOOTER_RADIUS * 2, WINDOW_WIDTH - SCOOTER_RADIUS * 2)
        y = random.randint(SCOOTER_RADIUS * 2, WINDOW_HEIGHT - SCOOTER_RADIUS * 2)
        scooter = Scooter(x, y)
        self.scooters.append(scooter)
        self.slider_value = len(self.scooters)
    
    def _adjust_scooter_count(self):
        """Adjust scooter count based on slider value"""
        target_count = self.slider_value
        current_count = len(self.scooters)
        
        if target_count > current_count:
            # Add scooters
            for _ in range(target_count - current_count):
                self._add_scooter()
        elif target_count < current_count:
            # Remove scooters (remove idle ones first)
            to_remove = current_count - target_count
            removed = 0
            for scooter in self.scooters[:]:
                if scooter.state == ScooterState.IDLE and removed < to_remove:
                    self.scooters.remove(scooter)
                    removed += 1
            # If still need to remove, remove any
            while removed < to_remove and self.scooters:
                self.scooters.pop()
                removed += 1
    
    def handle_events(self):
        """Handle pygame events"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # Left click
                    x, y = event.pos
                    # Check if clicking on slider
                    slider_rect = pygame.Rect(self.slider_x, self.slider_y, self.slider_width, self.slider_height)
                    if slider_rect.collidepoint(x, y):
                        self.slider_dragging = True
                        # Update slider value based on click position
                        rel_x = x - self.slider_x
                        self.slider_value = int(self.slider_min + (rel_x / self.slider_width) * (self.slider_max - self.slider_min))
                        self.slider_value = max(self.slider_min, min(self.slider_max, self.slider_value))
                        self._adjust_scooter_count()
                    elif self.pending_user_origin is None:
                        # First click: set origin
                        self.pending_user_origin = Point(x, y)
                    else:
                        # Second click: set destination and create user
                        destination = None
                        # Check if click is on a landmark
                        for landmark in self.landmarks:
                            if landmark.contains_point(Point(x, y), margin=20):
                                destination = landmark
                                break
                        
                        # If not on landmark, use click position
                        if destination is None:
                            destination = Point(x, y)
                        
                        # Create user with origin and destination
                        user = User(self.pending_user_origin.x, self.pending_user_origin.y, destination)
                        self.users.append(user)
                        # Auto-assign to closest idle scooter
                        self._assign_user_to_scooter(user)
                        # Reset pending origin
                        self.pending_user_origin = None
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_1:
                    # Toggle first-person view
                    if self.view_mode == "aerial":
                        self.view_mode = "first_person"
                        self.fp_scooter_index = 0
                elif event.key == pygame.K_a:
                    # Return to aerial view
                    self.view_mode = "aerial"
                elif event.key == pygame.K_EQUALS or (event.key == pygame.K_PLUS and event.mod & pygame.KMOD_SHIFT):
                    # Add a new scooter (+ key)
                    self._add_scooter()
            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    self.slider_dragging = False
            elif event.type == pygame.MOUSEMOTION:
                if self.slider_dragging:
                    x, y = event.pos
                    rel_x = x - self.slider_x
                    self.slider_value = int(self.slider_min + (rel_x / self.slider_width) * (self.slider_max - self.slider_min))
                    self.slider_value = max(self.slider_min, min(self.slider_max, self.slider_value))
                    self._adjust_scooter_count()
        
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
        """Assign user to closest idle scooter (ours first, then SPIN)"""
        # First, try to assign to our scooters
        min_dist = float('inf')
        closest_scooter = None
        
        for scooter in self.scooters:
            if scooter.state == ScooterState.IDLE and scooter.battery > 0:
                dist = scooter.distance_to(user.origin)
                if dist < min_dist:
                    min_dist = dist
                    closest_scooter = scooter
        
        if closest_scooter:
            closest_scooter.assign_user(user)
            # Track ride start time
            self.ride_start_times[id(user)] = pygame.time.get_ticks()
            self.our_active_users += 1
            return
        
        # If no idle our scooter, assign to SPIN
        min_dist = float('inf')
        closest_spin = None
        
        for spin_scooter in self.spin_scooters:
            if spin_scooter.available:
                dist = spin_scooter.distance_to(user.origin)
                if dist < min_dist:
                    min_dist = dist
                    closest_spin = spin_scooter
        
        if closest_spin:
            closest_spin.assign_user(user)
            # Create pedestrian to walk to SPIN scooter
            pedestrian = Pedestrian(user.origin.x, user.origin.y, closest_spin, user)
            self.pedestrians.append(pedestrian)
            # Track ride start time
            self.ride_start_times[id(user)] = pygame.time.get_ticks()
            self.spin_active_users += 1
        # If no scooter available, user will wait (shown in queue)
    
    def _spawn_pedestrian_user(self, use_our_scooters=True):
        """Spawn a new pedestrian/user at random location - OUR SCOOTERS GET PRIORITY"""
        # Random origin
        origin_x = random.randint(50, WINDOW_WIDTH - 50)
        origin_y = random.randint(50, WINDOW_HEIGHT - 50)
        
        # Random destination (either landmark or random point)
        if random.random() < 0.5 and self.landmarks:
            destination = random.choice(self.landmarks)
        else:
            dest_x = random.randint(50, WINDOW_WIDTH - 50)
            dest_y = random.randint(50, WINDOW_HEIGHT - 50)
            destination = Point(dest_x, dest_y)
        
        user = User(origin_x, origin_y, destination)
        self.users.append(user)
        
        # ALWAYS try our scooters first, regardless of use_our_scooters flag
        min_dist = float('inf')
        closest_scooter = None
        for scooter in self.scooters:
            if scooter.state == ScooterState.IDLE and scooter.battery > 0:
                dist = scooter.distance_to(user.origin)
                if dist < min_dist:
                    min_dist = dist
                    closest_scooter = scooter
        
        if closest_scooter:
            # Our scooter available - assign to it (PRIORITY!)
            closest_scooter.assign_user(user)
            self.ride_start_times[id(user)] = pygame.time.get_ticks()
            self.our_active_users += 1
        elif not use_our_scooters:
            # No our scooters available AND we're trying to fill SPIN quota - assign to SPIN
            min_dist = float('inf')
            closest_spin = None
            for spin_scooter in self.spin_scooters:
                if spin_scooter.available:
                    dist = spin_scooter.distance_to(user.origin)
                    if dist < min_dist:
                        min_dist = dist
                        closest_spin = spin_scooter
            if closest_spin:
                closest_spin.assign_user(user)
                pedestrian = Pedestrian(user.origin.x, user.origin.y, closest_spin, user)
                self.pedestrians.append(pedestrian)
                self.ride_start_times[id(user)] = pygame.time.get_ticks()
                self.spin_active_users += 1
        # If use_our_scooters=True but none available, user will wait and be assigned later
    
    def _maintain_pedestrian_count(self):
        """Maintain target pedestrian counts (3 our, 3 SPIN) - spawn max 1 per second, OUR SCOOTERS GET PRIORITY"""
        # Rate limiting: only spawn one pedestrian per second
        self.pedestrian_spawn_timer += 1
        if self.pedestrian_spawn_timer < PEDESTRIAN_SPAWN_INTERVAL:
            return  # Wait for next second
        
        # Reset timer
        self.pedestrian_spawn_timer = 0
        
        # Count current active pedestrians/users for our scooters
        our_count = sum(1 for u in self.users 
                       if hasattr(u, 'assigned_scooter') and u.assigned_scooter and 
                       not isinstance(u.assigned_scooter, SpinScooter) and
                       u.state != "completed")
        
        # Count SPIN users and pedestrians
        spin_user_count = sum(1 for u in self.users 
                             if hasattr(u, 'assigned_scooter') and u.assigned_scooter and 
                             isinstance(u.assigned_scooter, SpinScooter) and
                             u.state != "completed")
        spin_pedestrian_count = sum(1 for p in self.pedestrians 
                                    if p.state in ["walking_to_scooter", "riding"])
        spin_count = spin_user_count + spin_pedestrian_count
        
        # Check if we have available our scooters
        available_our_scooters = sum(1 for s in self.scooters 
                                    if s.state == ScooterState.IDLE and s.battery > 0)
        
        # ALWAYS prioritize our scooters - only use SPIN if no our scooters available
        if our_count < TARGET_PEDESTRIANS_OUR and available_our_scooters > 0:
            # Spawn for our scooters (they have priority!)
            self._spawn_pedestrian_user(use_our_scooters=True)
        elif spin_count < TARGET_PEDESTRIANS_SPIN and available_our_scooters == 0:
            # Only use SPIN if NO our scooters are available
            self._spawn_pedestrian_user(use_our_scooters=False)
        elif our_count < TARGET_PEDESTRIANS_OUR:
            # Still need more for our scooters, try to spawn (will wait if none available)
            self._spawn_pedestrian_user(use_our_scooters=True)
    
    def update(self):
        """Update all game objects"""
        # Update our scooters
        for scooter in self.scooters:
            scooter.update(self.users, self.charge_stations, self.obstacles, self.scooters)
        
        # Update SPIN scooters
        for spin_scooter in self.spin_scooters:
            spin_scooter.update(self.obstacles)
        
        # Update pedestrians
        for pedestrian in self.pedestrians[:]:
            pedestrian.update()
            # Remove pedestrians that are walking away and far enough
            if pedestrian.state == "walking_away":
                dist = math.sqrt((pedestrian.pos.x - pedestrian.target_scooter.pos.x)**2 + 
                               (pedestrian.pos.y - pedestrian.target_scooter.pos.y)**2)
                if dist > 100:  # Far enough away
                    self.pedestrians.remove(pedestrian)
        
        # Update users
        for user in self.users[:]:
            user.update()
            
            # Track completed rides and metrics
            if user.state == "completed":
                # Calculate ride duration
                user_id = id(user)
                if user_id in self.ride_start_times:
                    ride_duration = (pygame.time.get_ticks() - self.ride_start_times[user_id]) / 1000.0  # seconds
                    
                    # Determine if it was our scooter or SPIN
                    if hasattr(user, 'assigned_scooter'):
                        if isinstance(user.assigned_scooter, SpinScooter):
                            self.spin_rides_count += 1
                            self.spin_ride_times.append(ride_duration)
                            self.spin_active_users = max(0, self.spin_active_users - 1)
                        else:
                            self.our_rides_count += 1
                            self.our_ride_times.append(ride_duration)
                            self.our_active_users = max(0, self.our_active_users - 1)
                    
                    del self.ride_start_times[user_id]
                
                # Remove completed user
                if user in self.users:
                    self.users.remove(user)
        
        # Check for unassigned users and try to assign them
        for user in self.users:
            if user.assigned_scooter is None and user.state == "waiting":
                self._assign_user_to_scooter(user)
        
        # Auto-spawn pedestrians to maintain target counts
        self._maintain_pedestrian_count()
    
    def draw_aerial_view(self):
        """Draw aerial top-down view"""
        # Background
        self.screen.fill(COLOR_BACKGROUND)
        
        # Draw obstacles
        for obstacle in self.obstacles:
            pygame.draw.rect(self.screen, COLOR_OBSTACLE, obstacle.rect)
        
        # Draw landmarks
        for landmark in self.landmarks:
            pygame.draw.rect(self.screen, landmark.color, landmark.rect)
            text = self.small_font.render(landmark.name, True, COLOR_TEXT)
            text_rect = text.get_rect(center=(landmark.pos.x, landmark.pos.y))
            self.screen.blit(text, text_rect)
        
        # Draw charge stations
        for station in self.charge_stations:
            pygame.draw.rect(self.screen, COLOR_CHARGE_STATION, station.rect)
            text = self.small_font.render("CHARGE", True, COLOR_TEXT)
            text_rect = text.get_rect(center=(station.pos.x, station.pos.y))
            self.screen.blit(text, text_rect)
        
        # Draw pending user origin (if waiting for destination click)
        if self.pending_user_origin:
            pygame.draw.circle(self.screen, (255, 200, 0), 
                             (int(self.pending_user_origin.x), int(self.pending_user_origin.y)), 
                             USER_RADIUS + 3, 2)
            text = self.small_font.render("Click destination", True, (255, 255, 0))
            text_rect = text.get_rect(center=(int(self.pending_user_origin.x), 
                                            int(self.pending_user_origin.y) - 25))
            self.screen.blit(text, text_rect)
        
        # Draw users
        for user in self.users:
            # Draw origin
            pulse = abs(math.sin(user.pulse_phase)) * 0.3 + 0.7
            radius = int(USER_RADIUS * pulse)
            pygame.draw.circle(self.screen, COLOR_USER, (int(user.origin.x), int(user.origin.y)), radius)
            
            # Draw destination if set
            if user.destination:
                dest_point = user.get_destination_point()
                pygame.draw.circle(self.screen, (0, 255, 0), 
                                 (int(dest_point.x), int(dest_point.y)), 
                                 USER_RADIUS, 2)
                # Draw line from origin to destination
                pygame.draw.line(self.screen, (200, 200, 200), 
                               (int(user.origin.x), int(user.origin.y)),
                               (int(dest_point.x), int(dest_point.y)), 1)
            
            # Waiting indicator if not assigned
            if user.assigned_scooter is None and user.state == "waiting":
                text = self.small_font.render("?", True, COLOR_TEXT)
                text_rect = text.get_rect(center=(int(user.origin.x), int(user.origin.y)))
                self.screen.blit(text, text_rect)
        
        # Draw SPIN scooters
        for spin_scooter in self.spin_scooters:
            color = SPIN_COLOR if spin_scooter.available else (200, 50, 50)
            # Draw scooter circle
            pygame.draw.circle(self.screen, color, (int(spin_scooter.pos.x), int(spin_scooter.pos.y)), SCOOTER_RADIUS)
            # Draw direction arrow if moving
            if spin_scooter.velocity > 0:
                arrow_length = SCOOTER_RADIUS + 5
                end_x = spin_scooter.pos.x + math.cos(spin_scooter.angle) * arrow_length
                end_y = spin_scooter.pos.y + math.sin(spin_scooter.angle) * arrow_length
                pygame.draw.line(self.screen, COLOR_TEXT, 
                               (int(spin_scooter.pos.x), int(spin_scooter.pos.y)),
                               (int(end_x), int(end_y)), 2)
            # Draw "SPIN" label
            text = self.small_font.render("SPIN", True, COLOR_TEXT)
            text_rect = text.get_rect(center=(int(spin_scooter.pos.x), int(spin_scooter.pos.y)))
            self.screen.blit(text, text_rect)
        
        # Draw pedestrians (MAKE THEM IMPOSSIBLE TO MISS!)
        for pedestrian in self.pedestrians:
            # ALWAYS draw pedestrians - make them HUGE and BRIGHT
            if pedestrian.state == "walking_to_scooter":
                color = (255, 0, 255)  # Bright magenta
                radius = 15  # MUCH larger
            elif pedestrian.state == "riding":
                color = (200, 0, 200)  # Purple
                radius = 12
            else:
                color = (150, 0, 150)  # Darker purple
                radius = 10
            
            # Draw main circle - VERY VISIBLE
            pygame.draw.circle(self.screen, color, 
                             (int(pedestrian.pos.x), int(pedestrian.pos.y)), 
                             radius)
            # Draw thick white outline for maximum visibility
            pygame.draw.circle(self.screen, (255, 255, 255), 
                             (int(pedestrian.pos.x), int(pedestrian.pos.y)), 
                             radius, 3)
            # Draw inner yellow highlight
            pygame.draw.circle(self.screen, (255, 255, 0), 
                             (int(pedestrian.pos.x), int(pedestrian.pos.y)), 
                             radius - 4)
            
            # Draw line to target if walking to scooter - BRIGHT YELLOW
            if pedestrian.state == "walking_to_scooter":
                pygame.draw.line(self.screen, (255, 255, 0),  # Bright yellow line
                               (int(pedestrian.pos.x), int(pedestrian.pos.y)),
                               (int(pedestrian.target_scooter.pos.x), int(pedestrian.target_scooter.pos.y)), 4)
                # Draw arrow pointing to scooter
                dx = pedestrian.target_scooter.pos.x - pedestrian.pos.x
                dy = pedestrian.target_scooter.pos.y - pedestrian.pos.y
                if dx != 0 or dy != 0:
                    angle = math.atan2(dy, dx)
                    arrow_x = pedestrian.pos.x + math.cos(angle) * (radius + 8)
                    arrow_y = pedestrian.pos.y + math.sin(angle) * (radius + 8)
                    pygame.draw.circle(self.screen, (255, 255, 0), (int(arrow_x), int(arrow_y)), 5)
        
        # Draw our scooters
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
        """Draw HUD overlay with fleet stats and comparison metrics"""
        # Calculate our stats
        idle_count = sum(1 for s in self.scooters if s.state == ScooterState.IDLE)
        idle_percent = (idle_count / len(self.scooters)) * 100 if self.scooters else 0
        avg_battery = sum(s.battery for s in self.scooters) / len(self.scooters) if self.scooters else 0
        
        # Calculate comparison metrics
        our_avg_time = sum(self.our_ride_times) / len(self.our_ride_times) if self.our_ride_times else 0
        spin_avg_time = sum(self.spin_ride_times) / len(self.spin_ride_times) if self.spin_ride_times else 0
        
        # Draw main HUD background
        hud_rect = pygame.Rect(10, 10, 280, 140)
        pygame.draw.rect(self.screen, (0, 0, 0, 200), hud_rect)
        pygame.draw.rect(self.screen, (255, 255, 255), hud_rect, 2)
        
        # Draw stats
        y_offset = 20
        stats = [
            f"Our Scooters: {len(self.scooters)}",
            f"Idle: {idle_percent:.1f}% | Battery: {avg_battery:.1f}%",
            f"Click 1: origin, Click 2: destination",
            f"Press '+' to add scooter"
        ]
        
        for stat in stats:
            text = self.small_font.render(stat, True, COLOR_TEXT)
            self.screen.blit(text, (20, y_offset))
            y_offset += 18
        
        # Draw slider for scooter count
        slider_label = self.small_font.render("Scooters:", True, COLOR_TEXT)
        self.screen.blit(slider_label, (20, y_offset))
        
        # Slider track
        slider_rect = pygame.Rect(self.slider_x, self.slider_y, self.slider_width, self.slider_height)
        pygame.draw.rect(self.screen, (100, 100, 100), slider_rect)
        pygame.draw.rect(self.screen, (200, 200, 200), slider_rect, 2)
        
        # Slider handle position
        handle_pos = self.slider_x + ((self.slider_value - self.slider_min) / (self.slider_max - self.slider_min)) * self.slider_width
        handle_rect = pygame.Rect(int(handle_pos - 5), self.slider_y - 2, 10, self.slider_height + 4)
        pygame.draw.rect(self.screen, (100, 200, 255), handle_rect)
        pygame.draw.rect(self.screen, (255, 255, 255), handle_rect, 2)
        
        # Slider value text
        value_text = self.small_font.render(str(self.slider_value), True, COLOR_TEXT)
        self.screen.blit(value_text, (self.slider_x + self.slider_width + 10, self.slider_y))
        
        # Draw comparison panel
        comp_rect = pygame.Rect(10, 160, 350, 120)
        pygame.draw.rect(self.screen, (0, 0, 0, 200), comp_rect)
        pygame.draw.rect(self.screen, (255, 255, 255), comp_rect, 2)
        
        y_offset = 170
        # Header
        header_text = self.small_font.render("COMPARISON METRICS", True, (255, 255, 0))
        self.screen.blit(header_text, (20, y_offset))
        y_offset += 20
        
        # Our rides
        our_text = self.small_font.render(f"OUR Rides: {self.our_rides_count}", True, (50, 200, 255))
        self.screen.blit(our_text, (20, y_offset))
        if self.our_ride_times:
            time_text = self.small_font.render(f"  Avg Time: {our_avg_time:.1f}s", True, (150, 200, 255))
            self.screen.blit(time_text, (180, y_offset))
        y_offset += 18
        
        # SPIN rides
        spin_text = self.small_font.render(f"SPIN Rides: {self.spin_rides_count}", True, SPIN_COLOR)
        self.screen.blit(spin_text, (20, y_offset))
        if self.spin_ride_times:
            time_text = self.small_font.render(f"  Avg Time: {spin_avg_time:.1f}s", True, (255, 150, 100))
            self.screen.blit(time_text, (180, y_offset))
        y_offset += 18
        
        # Active users
        active_text = self.small_font.render(f"Active: Our {self.our_active_users} | SPIN {self.spin_active_users}", True, COLOR_TEXT)
        self.screen.blit(active_text, (20, y_offset))
        y_offset += 18
        
        # DEBUG: Show pedestrian count
        ped_text = self.small_font.render(f"Pedestrians: {len(self.pedestrians)}", True, (255, 255, 0))
        self.screen.blit(ped_text, (20, y_offset))
        
        # Visual comparison bar
        total_rides = self.our_rides_count + self.spin_rides_count
        if total_rides > 0:
            bar_width = 300
            our_width = int((self.our_rides_count / total_rides) * bar_width)
            bar_y = y_offset + 20
            # Our bar (blue)
            pygame.draw.rect(self.screen, (50, 200, 255), (20, bar_y, our_width, 15))
            # SPIN bar (orange)
            pygame.draw.rect(self.screen, SPIN_COLOR, (20 + our_width, bar_y, bar_width - our_width, 15))
            # Border
            pygame.draw.rect(self.screen, (255, 255, 255), (20, bar_y, bar_width, 15), 1)
    
    def draw_first_person_view(self):
        """Draw realistic first-person road perspective view"""
        if not self.scooters or self.fp_scooter_index >= len(self.scooters):
            self.view_mode = "aerial"
            return
        
        scooter = self.scooters[self.fp_scooter_index]
        
        # Sky gradient
        horizon_y = int(WINDOW_HEIGHT * 0.6)
        for y in range(horizon_y):
            ratio = y / horizon_y
            color = (
                int(135 + (200 - 135) * ratio),  # R
                int(206 + (220 - 206) * ratio),  # G
                int(235 + (255 - 235) * ratio)   # B
            )
            pygame.draw.line(self.screen, color, (0, y), (WINDOW_WIDTH, y))
        
        # Road surface (below horizon)
        road_color = (100, 100, 100)
        pygame.draw.rect(self.screen, road_color, 
                        (0, horizon_y, WINDOW_WIDTH, WINDOW_HEIGHT - horizon_y))
        
        # Road perspective grid (converging lines)
        center_x = WINDOW_WIDTH // 2
        vanishing_point_y = horizon_y
        
        # Center line
        for i in range(20):
            y = horizon_y + i * 15
            if y >= WINDOW_HEIGHT:
                break
            # Calculate width based on perspective
            depth = (y - horizon_y) / (WINDOW_HEIGHT - horizon_y)
            road_width = WINDOW_WIDTH * (0.3 + depth * 0.7)
            x_offset = (WINDOW_WIDTH - road_width) / 2
            
            # Center line
            if i % 2 == 0:
                line_x = center_x
                pygame.draw.line(self.screen, (255, 255, 0), 
                               (int(line_x - 2), int(y)), 
                               (int(line_x + 2), int(y)), 2)
            
            # Road edges
            pygame.draw.line(self.screen, (255, 255, 255),
                           (int(x_offset), int(y)),
                           (int(x_offset + 5), int(y)), 2)
            pygame.draw.line(self.screen, (255, 255, 255),
                           (int(WINDOW_WIDTH - x_offset), int(y)),
                           (int(WINDOW_WIDTH - x_offset - 5), int(y)), 2)
        
        # Side lines (converging to vanishing point)
        for side in [-1, 1]:
            for i in range(10):
                y = horizon_y + i * 40
                if y >= WINDOW_HEIGHT:
                    break
                depth = (y - horizon_y) / (WINDOW_HEIGHT - horizon_y)
                road_width = WINDOW_WIDTH * (0.3 + depth * 0.7)
                x = center_x + side * road_width / 2
                pygame.draw.circle(self.screen, (200, 200, 200), 
                                 (int(x), int(y)), 3)
        
        # Helper function to project 3D point to screen
        def project_to_screen(world_x, world_y, world_z=0):
            """Project 3D world coordinates to 2D screen with perspective"""
            # Calculate relative position
            dx = world_x - scooter.pos.x
            dy = world_y - scooter.pos.y
            
            # Rotate to scooter's perspective
            angle_to_obj = math.atan2(dy, dx) - scooter.angle
            distance = math.sqrt(dx * dx + dy * dy)
            
            # Field of view limits (90 degrees)
            if abs(angle_to_obj) > math.pi / 2:
                return None, None, None, None
            
            # Perspective projection
            fov = math.pi / 2  # 90 degrees
            screen_x = center_x + math.sin(angle_to_obj) * (WINDOW_WIDTH / 2) / math.tan(fov / 2)
            
            # Depth affects vertical position and size
            depth_factor = distance / 500.0  # Normalize to reasonable distance
            screen_y = horizon_y - (1.0 / (1.0 + depth_factor)) * (WINDOW_HEIGHT - horizon_y)
            size = max(5, 150 / (1.0 + depth_factor))
            
            return int(screen_x), int(screen_y), int(size), distance
        
        # Draw obstacles in 3D perspective
        obstacle_data = []
        for obstacle in self.obstacles:
            screen_x, screen_y, size, dist = project_to_screen(obstacle.rect.centerx, obstacle.rect.centery, 30)
            if screen_x is not None and dist < 400 and screen_y < WINDOW_HEIGHT:
                obstacle_data.append((screen_x, screen_y, size, dist, COLOR_OBSTACLE))
        
        # Draw other scooters in 3D
        for other_scooter in self.scooters:
            if other_scooter is scooter or other_scooter.state == ScooterState.DEAD:
                continue
            screen_x, screen_y, size, dist = project_to_screen(other_scooter.pos.x, other_scooter.pos.y, 15)
            if screen_x is not None and dist < 400 and screen_y < WINDOW_HEIGHT:
                color = other_scooter.get_color()
                obstacle_data.append((screen_x, screen_y, size, dist, color))
        
        # Draw landmarks in 3D
        for landmark in self.landmarks:
            screen_x, screen_y, size, dist = project_to_screen(landmark.pos.x, landmark.pos.y, 40)
            if screen_x is not None and dist < 500 and screen_y < WINDOW_HEIGHT:
                obstacle_data.append((screen_x, screen_y, size, dist, landmark.color))
        
        # Sort by distance (draw far objects first)
        obstacle_data.sort(key=lambda x: x[3], reverse=True)
        
        # Draw all 3D objects
        for screen_x, screen_y, size, dist, color in obstacle_data:
            if screen_y >= horizon_y and screen_y < WINDOW_HEIGHT:
                # Draw as 3D box
                height = size
                width = size * 0.6
                # Base rectangle
                pygame.draw.rect(self.screen, color,
                               (screen_x - width // 2, screen_y - height, width, height))
                # Top (perspective)
                top_color = tuple(min(255, c + 30) for c in color)
                pygame.draw.polygon(self.screen, top_color, [
                    (screen_x - width // 2, screen_y - height),
                    (screen_x - width // 4, screen_y - height - size * 0.3),
                    (screen_x + width // 4, screen_y - height - size * 0.3),
                    (screen_x + width // 2, screen_y - height)
                ])
        
        # Speed lines (motion blur effect)
        if scooter.velocity > 1.0:
            for i in range(5):
                y = horizon_y + random.randint(0, WINDOW_HEIGHT - horizon_y)
                x_offset = random.randint(-50, 50)
                pygame.draw.line(self.screen, (150, 150, 150, 100),
                               (center_x + x_offset, y),
                               (center_x + x_offset + random.randint(-20, 20), y + 10), 1)
        
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
            
            # Only show arrow if target is in front
            if abs(target_angle) < math.pi / 2:
                # Draw arrow on screen (centered, pointing to target)
                arrow_x = center_x + math.sin(target_angle) * 150
                arrow_y = horizon_y - 50
                
                # Draw arrow line
                pygame.draw.line(self.screen, (255, 255, 0), 
                               (center_x, horizon_y - 20), (int(arrow_x), int(arrow_y)), 3)
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
