import math
import pygame
import pymunk
import pymunk.pygame_util


WIDTH, HEIGHT = 1100, 800
FPS = 60

PIVOT_POS = (360, 400)

DOOR_LENGTH = 360
DOOR_THICKNESS = 28
DOOR_MASS = 8.0

PUSH_FORCE = 9000
PUSH_TIME = 0.18

HANDLE_LOCAL_X = DOOR_LENGTH / 2
NEAR_HINGE_LOCAL_X = -DOOR_LENGTH / 2 + 55

HOLD_MOTOR_FORCE = 8_000_000


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
        start_angle = math.radians(-40)
        end_angle = math.radians(90)
    else:
        start_angle = math.radians(90)
        end_angle = math.radians(-40)

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


def create_door(space):
    moment = pymunk.moment_for_box(DOOR_MASS, (DOOR_LENGTH, DOOR_THICKNESS))
    body = pymunk.Body(DOOR_MASS, moment)

    body.position = (
        PIVOT_POS[0] + DOOR_LENGTH / 2,
        PIVOT_POS[1],
    )
    body.angle = 0.0

    shape = pymunk.Poly.create_box(body, (DOOR_LENGTH, DOOR_THICKNESS))
    shape.color = pygame.Color(160, 95, 45, 255)
    shape.friction = 0.8

    hinge = pymunk.PivotJoint(
        space.static_body,
        body,
        PIVOT_POS,
        (-DOOR_LENGTH / 2, 0),
    )
    hinge.collide_bodies = False

    hold_motor = pymunk.SimpleMotor(space.static_body, body, 0.0)
    hold_motor.max_force = HOLD_MOTOR_FORCE

    space.add(body, shape, hinge, hold_motor)

    return body, hold_motor


def reset(space):
    for item in list(space.constraints) + list(space.shapes) + list(space.bodies):
        space.remove(item)

    door, hold_motor = create_door(space)
    return door, hold_motor


def world_point(body, local_x):
    p = body.local_to_world((local_x, 0))
    return p.x, p.y


def calculate_torque(point, force):
    rx = point[0] - PIVOT_POS[0]
    ry = point[1] - PIVOT_POS[1]

    fx, fy = force

    # 2D cross product: tau = r_x F_y - r_y F_x
    return rx * fy - ry * fx


def main():
    pygame.init()

    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Door Torque Demo")

    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Arial", 24)
    small_font = pygame.font.SysFont("Arial", 20)

    space = pymunk.Space()
    space.gravity = (0, 0)

    draw_options = pymunk.pygame_util.DrawOptions(screen)

    door, hold_motor = reset(space)

    free_mode = False
    push_timer = 0.0
    push_local_x = HANDLE_LOCAL_X

    running = True

    while running:
        dt = 1.0 / FPS

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_g:
                    free_mode = not free_mode

                if event.key == pygame.K_p:
                    push_local_x = HANDLE_LOCAL_X
                    push_timer = PUSH_TIME

                if event.key == pygame.K_h:
                    push_local_x = NEAR_HINGE_LOCAL_X
                    push_timer = PUSH_TIME

                if event.key == pygame.K_r:
                    door, hold_motor = reset(space)
                    free_mode = False
                    push_timer = 0.0
                    push_local_x = HANDLE_LOCAL_X

        if free_mode:
            hold_motor.max_force = 0.0
        else:
            hold_motor.rate = 0.0
            hold_motor.max_force = HOLD_MOTOR_FORCE
            door.angular_velocity = 0.0
            door.angle = 0.0

        push_point = world_point(door, push_local_x)

        # 推门方向：垂直于门板
        angle = door.angle
        force_dir = (-math.sin(angle), math.cos(angle))
        force = (force_dir[0] * PUSH_FORCE, force_dir[1] * PUSH_FORCE)

        tau_push = 0.0

        if push_timer > 0:
            door.apply_force_at_world_point(force, push_point)
            tau_push = calculate_torque(push_point, force)
            push_timer -= dt
        else:
            tau_push = calculate_torque(push_point, force)

        space.step(dt)

        screen.fill((250, 250, 250))
        space.debug_draw(draw_options)

        pivot = PIVOT_POS
        handle = world_point(door, HANDLE_LOCAL_X)
        near_hinge = world_point(door, NEAR_HINGE_LOCAL_X)
        push_point = world_point(door, push_local_x)

        pivot_i = (int(pivot[0]), int(pivot[1]))
        handle_i = (int(handle[0]), int(handle[1]))
        near_i = (int(near_hinge[0]), int(near_hinge[1]))
        push_i = (int(push_point[0]), int(push_point[1]))

        pygame.draw.circle(screen, (20, 20, 20), pivot_i, 13)
        pygame.draw.circle(screen, (20, 20, 20), handle_i, 8)
        pygame.draw.circle(screen, (80, 80, 80), near_i, 6)

        # 力臂
        pygame.draw.line(screen, (0, 80, 190), pivot_i, push_i, 4)

        # 推力箭头
        arrow_len = 120
        force_arrow_end = (
            int(push_i[0] + force_dir[0] * arrow_len),
            int(push_i[1] + force_dir[1] * arrow_len),
        )
        draw_arrow(screen, push_i, force_arrow_end, (220, 0, 0), 5)

        # 力矩圆弧
        draw_arc_arrow(
            screen,
            pivot_i,
            65,
            clockwise=(tau_push > 0),
            color=(255, 140, 0),
            width=5,
        )

        # 文字
        title = font.render("Door torque demo", True, (0, 40, 120))
        screen.blit(title, (30, 30))

        screen.blit(small_font.render("G: switch HOLD / FREE", True, (20, 20, 20)), (30, 75))
        screen.blit(small_font.render("P: push at handle", True, (0, 120, 60)), (30, 105))
        screen.blit(small_font.render("H: push near hinge", True, (180, 80, 0)), (30, 135))
        screen.blit(small_font.render("R: reset", True, (60, 60, 60)), (30, 165))

        mode_text = "Mode: FREE" if free_mode else "Mode: HOLD"
        mode_color = (180, 0, 0) if free_mode else (0, 120, 60)
        screen.blit(font.render(mode_text, True, mode_color), (780, 40))

        push_name = "handle" if push_local_x == HANDLE_LOCAL_X else "near hinge"
        screen.blit(
            small_font.render(f"Push position: {push_name}", True, (20, 20, 20)),
            (780, 85),
        )

        rx = push_point[0] - PIVOT_POS[0]
        ry = push_point[1] - PIVOT_POS[1]
        lever_arm = math.sqrt(rx * rx + ry * ry)

        screen.blit(
            small_font.render(f"lever arm r = {lever_arm:.0f} px", True, (0, 80, 190)),
            (780, 120),
        )

        screen.blit(
            small_font.render(f"force F = {PUSH_FORCE:.0f}", True, (180, 0, 0)),
            (780, 150),
        )

        screen.blit(
            small_font.render(f"torque tau = {tau_push:.0f}", True, (210, 100, 0)),
            (780, 180),
        )

        screen.blit(
            small_font.render("Torque = force x lever arm", True, (20, 20, 20)),
            (780, 220),
        )

        screen.blit(
            small_font.render("Pushing far from hinge makes larger torque.", True, (20, 20, 20)),
            (780, 250),
        )

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()


if __name__ == "__main__":
    main()