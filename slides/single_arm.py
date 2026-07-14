import math
import pygame
import pymunk
import pymunk.pygame_util


WIDTH, HEIGHT = 1100, 800
FPS = 60

GRAVITY = 900

PIVOT_POS = (500, 430)

ROD_LENGTH = 260
ROD_THICKNESS = 18
ROD_MASS = 1.8
DUMBBELL_MASS = 8.0

MOTOR_RATE = -2.5
MOTOR_FORCE = 1_200_000

HOLD_MOTOR_FORCE = 5_000_000


def draw_arrow(screen, start, end, color, width=4):
    pygame.draw.line(screen, color, start, end, width)

    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    head_len = 18
    head_angle = math.pi / 7

    p1 = (
        end[0] - head_len * math.cos(angle - head_angle),
        end[1] - head_len * math.sin(angle - head_angle),
    )
    p2 = (
        end[0] - head_len * math.cos(angle + head_angle),
        end[1] - head_len * math.sin(angle + head_angle),
    )

    pygame.draw.polygon(screen, color, [end, p1, p2])


def draw_arc_arrow(screen, center, radius, clockwise, color, width=5):
    if clockwise:
        start_angle = math.radians(-30)
        end_angle = math.radians(100)
    else:
        start_angle = math.radians(100)
        end_angle = math.radians(-30)

    points = []
    steps = 36

    for i in range(steps + 1):
        t = i / steps
        angle = start_angle + (end_angle - start_angle) * t
        points.append(
            (
                center[0] + radius * math.cos(angle),
                center[1] + radius * math.sin(angle),
            )
        )

    pygame.draw.lines(screen, color, False, points, width)

    end = points[-1]
    prev = points[-2]
    angle = math.atan2(end[1] - prev[1], end[0] - prev[0])

    head_len = 16
    head_angle = math.pi / 6

    p1 = (
        end[0] - head_len * math.cos(angle - head_angle),
        end[1] - head_len * math.sin(angle - head_angle),
    )
    p2 = (
        end[0] - head_len * math.cos(angle + head_angle),
        end[1] - head_len * math.sin(angle + head_angle),
    )

    pygame.draw.polygon(screen, color, [end, p1, p2])


def create_rod(space):
    moment = pymunk.moment_for_box(ROD_MASS, (ROD_LENGTH, ROD_THICKNESS))
    body = pymunk.Body(ROD_MASS, moment)

    body.position = (
        PIVOT_POS[0] + ROD_LENGTH / 2,
        PIVOT_POS[1],
    )
    body.angle = 0.0

    shape = pymunk.Poly.create_box(body, (ROD_LENGTH, ROD_THICKNESS))
    shape.color = pygame.Color(220, 175, 120, 255)
    shape.friction = 0.8

    pivot_joint = pymunk.PivotJoint(
        space.static_body,
        body,
        PIVOT_POS,
        (-ROD_LENGTH / 2, 0),
    )
    pivot_joint.collide_bodies = False

    motor = pymunk.SimpleMotor(space.static_body, body, 0.0)
    motor.max_force = HOLD_MOTOR_FORCE

    space.add(body, shape, pivot_joint, motor)

    return body, motor


def create_dumbbell(space, rod):
    end_pos = rod.local_to_world((ROD_LENGTH / 2, 0))

    moment = pymunk.moment_for_circle(DUMBBELL_MASS, 0, 34)
    body = pymunk.Body(DUMBBELL_MASS, moment)
    body.position = end_pos

    shape = pymunk.Circle(body, 34)
    shape.color = pygame.Color(45, 45, 45, 255)
    shape.friction = 0.8

    joint = pymunk.PinJoint(
        rod,
        body,
        (ROD_LENGTH / 2, 0),
        (0, 0),
    )
    joint.distance = 0
    joint.collide_bodies = False

    space.add(body, shape, joint)

    return body


def endpoint(body, local_x):
    p = body.local_to_world((local_x, 0))
    return int(p.x), int(p.y)


def reset(space):
    for item in list(space.constraints) + list(space.shapes) + list(space.bodies):
        space.remove(item)

    rod, motor = create_rod(space)
    dumbbell = create_dumbbell(space, rod)

    return rod, dumbbell, motor


def calculate_gravity_torque(dumbbell_pos):
    rx = dumbbell_pos[0] - PIVOT_POS[0]
    force_y = DUMBBELL_MASS * GRAVITY

    # screen coordinate: downward is positive y
    # positive value here means clockwise visual torque
    torque = rx * force_y
    return torque


def main():
    pygame.init()

    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("One Rod Torque Demo")

    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Arial", 24)
    small_font = pygame.font.SysFont("Arial", 20)

    space = pymunk.Space()
    space.gravity = (0, GRAVITY)

    draw_options = pymunk.pygame_util.DrawOptions(screen)

    rod, dumbbell, motor = reset(space)

    gravity_mode = False
    motor_on = False
    running = True

    while running:
        dt = 1.0 / FPS

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_g:
                    gravity_mode = not gravity_mode
                    motor_on = False

                if event.key == pygame.K_b:
                    motor_on = not motor_on

                if event.key == pygame.K_r:
                    rod, dumbbell, motor = reset(space)
                    gravity_mode = False
                    motor_on = False

        dumbbell_pos_float = (
            dumbbell.position.x,
            dumbbell.position.y,
        )

        tau_gravity = calculate_gravity_torque(dumbbell_pos_float)

        tau_motor = 0.0

        if gravity_mode:
            if motor_on:
                motor.rate = MOTOR_RATE
                motor.max_force = MOTOR_FORCE
                tau_motor = -MOTOR_FORCE
            else:
                motor.rate = 0.0
                motor.max_force = 0.0
        else:
            motor.rate = 0.0
            motor.max_force = HOLD_MOTOR_FORCE
            rod.angular_velocity = 0.0
            rod.angle = 0.0
            tau_motor = -tau_gravity

        tau_total = tau_gravity + tau_motor

        space.step(dt)

        screen.fill((250, 250, 250))
        space.debug_draw(draw_options)

        pivot = PIVOT_POS
        hand = endpoint(rod, ROD_LENGTH / 2)
        dumbbell_pos = (int(dumbbell.position.x), int(dumbbell.position.y))

        pygame.draw.circle(screen, (20, 20, 20), pivot, 11)
        pygame.draw.circle(screen, (20, 20, 20), hand, 7)

        pygame.draw.line(screen, (0, 80, 190), pivot, dumbbell_pos, 4)

        gravity_start = (dumbbell_pos[0], dumbbell_pos[1] - 75)
        gravity_end = (dumbbell_pos[0], dumbbell_pos[1] + 75)
        draw_arrow(screen, gravity_start, gravity_end, (220, 0, 0), 5)

        # 旋转轴旁边的力矩方向图
        if abs(tau_gravity) > 1e-6:
            draw_arc_arrow(
                screen,
                pivot,
                60,
                clockwise=(tau_gravity > 0),
                color=(255, 140, 0),
                width=5,
            )

        # 力矩文字，显示在旋转轴旁边
        torque_x = pivot[0] - 180
        torque_y = pivot[1] + 30

        screen.blit(
            small_font.render(f"tau_g = {tau_gravity:.0f} N*m", True, (210, 100, 0)),
            (torque_x, torque_y),
        )
        screen.blit(
            small_font.render(f"tau_motor = {tau_motor:.0f} N*m", True, (0, 130, 60)),
            (torque_x, torque_y + 28),
        )
        screen.blit(
            small_font.render(f"tau_total = {tau_total:.0f} N*m", True, (120, 0, 180)),
            (torque_x, torque_y + 56),
        )

        title = font.render("One rod with dumbbell", True, (0, 40, 120))
        screen.blit(title, (30, 30))

        screen.blit(small_font.render("G: switch HOLD / GRAVITY", True, (20, 20, 20)), (30, 75))
        screen.blit(small_font.render("B: motor on/off", True, (0, 120, 60)), (30, 105))
        screen.blit(small_font.render("R: reset", True, (60, 60, 60)), (30, 135))

        mode_text = "Mode: GRAVITY" if gravity_mode else "Mode: HOLD"
        mode_color = (180, 0, 0) if gravity_mode else (0, 120, 60)
        screen.blit(font.render(mode_text, True, mode_color), (760, 40))

        motor_text = "Motor ON" if motor_on else "Motor OFF"
        motor_color = (0, 140, 60) if motor_on else (120, 120, 120)
        screen.blit(font.render(motor_text, True, motor_color), (760, 80))

        screen.blit(
            small_font.render("Red: dumbbell weight F = mg", True, (180, 0, 0)),
            (30, 175),
        )
        screen.blit(
            small_font.render("Blue: moment arm from pivot to dumbbell", True, (0, 80, 190)),
            (30, 205),
        )

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()


if __name__ == "__main__":
    main()