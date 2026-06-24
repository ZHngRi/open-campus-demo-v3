import math
import pygame
import pymunk
import pymunk.pygame_util


WIDTH, HEIGHT = 1000, 650
FPS = 60

SHOULDER_POS = (500, 320)

ARM_LENGTH = 360
ARM_THICKNESS = 18
ARM_MASS = 2.0

DUMBBELL_MASS = 4.0
GRAVITY = 900

MUSCLE_TORQUE = 2_800_000

TANGENTIAL_ARROW_SCALE = 0.025
TANGENTIAL_ARROW_MIN = 20
TANGENTIAL_ARROW_MAX = 180


def draw_arrow(screen, start, end, color, width=4):
    pygame.draw.line(screen, color, start, end, width)

    sx, sy = start
    ex, ey = end
    angle = math.atan2(ey - sy, ex - sx)

    head_len = 18
    head_angle = math.pi / 7

    p1 = (
        ex - head_len * math.cos(angle - head_angle),
        ey - head_len * math.sin(angle - head_angle),
    )
    p2 = (
        ex - head_len * math.cos(angle + head_angle),
        ey - head_len * math.sin(angle + head_angle),
    )

    pygame.draw.polygon(screen, color, [end, p1, p2])


def draw_arc_arrow(screen, center, radius, start_angle, end_angle, color, width=5):
    rect = pygame.Rect(
        center[0] - radius,
        center[1] - radius,
        radius * 2,
        radius * 2,
    )

    pygame.draw.arc(screen, color, rect, start_angle, end_angle, width)

    angle = end_angle
    end = (
        center[0] + radius * math.cos(angle),
        center[1] + radius * math.sin(angle),
    )

    tangent = angle + math.pi / 2

    head_len = 16
    p1 = (
        end[0] - head_len * math.cos(tangent - math.pi / 6),
        end[1] - head_len * math.sin(tangent - math.pi / 6),
    )
    p2 = (
        end[0] - head_len * math.cos(tangent + math.pi / 6),
        end[1] - head_len * math.sin(tangent + math.pi / 6),
    )

    pygame.draw.polygon(screen, color, [end, p1, p2])


def create_arm(space):
    moment = pymunk.moment_for_box(ARM_MASS, (ARM_LENGTH, ARM_THICKNESS))

    body = pymunk.Body(ARM_MASS, moment)
    body.position = SHOULDER_POS[0] + ARM_LENGTH / 2, SHOULDER_POS[1]
    body.angle = 0

    shape = pymunk.Poly.create_box(body, (ARM_LENGTH, ARM_THICKNESS))
    shape.friction = 0.8
    shape.color = pygame.Color(220, 180, 120, 255)

    shoulder_joint = pymunk.PivotJoint(
        space.static_body,
        body,
        SHOULDER_POS,
    )

    shoulder_joint.collide_bodies = False

    space.add(body, shape, shoulder_joint)

    return body


def create_dumbbell(space, arm_body):
    end_local = (ARM_LENGTH / 2, 0)

    moment = pymunk.moment_for_circle(DUMBBELL_MASS, 0, 30)
    body = pymunk.Body(DUMBBELL_MASS, moment)

    end_world = arm_body.local_to_world(end_local)
    body.position = end_world

    shape = pymunk.Circle(body, 30)
    shape.friction = 0.8
    shape.color = pygame.Color(60, 60, 60, 255)

    joint = pymunk.PinJoint(arm_body, body, end_local, (0, 0))
    joint.distance = 0
    joint.collide_bodies = False

    space.add(body, shape, joint)

    return body


def reset(space):
    for item in list(space.bodies) + list(space.shapes) + list(space.constraints):
        space.remove(item)

    arm = create_arm(space)
    dumbbell = create_dumbbell(space, arm)

    return arm, dumbbell


def get_radius_vector(shoulder, point):
    rx = point[0] - shoulder[0]
    ry = point[1] - shoulder[1]

    radius = math.sqrt(rx * rx + ry * ry)

    if radius < 1e-6:
        return 0, 0, 0

    return rx / radius, ry / radius, radius


def get_tangent_vector_from_angular_acceleration(shoulder, point, angular_acceleration):
    ux, uy, radius = get_radius_vector(shoulder, point)

    if angular_acceleration >= 0:
        tx = -uy
        ty = ux
    else:
        tx = uy
        ty = -ux

    return tx, ty, radius


def clamp(value, min_value, max_value):
    return max(min_value, min(value, max_value))


def main():
    pygame.init()

    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Arm Torque Demo")

    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Arial", 24)
    small_font = pygame.font.SysFont("Arial", 20)

    space = pymunk.Space()
    space.gravity = (0, GRAVITY)

    draw_options = pymunk.pygame_util.DrawOptions(screen)

    arm, dumbbell = reset(space)

    muscle_on = False
    running = True

    previous_angular_velocity = arm.angular_velocity

    while running:
        dt = 1.0 / FPS

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_m:
                    muscle_on = not muscle_on

                if event.key == pygame.K_r:
                    arm, dumbbell = reset(space)
                    muscle_on = False
                    previous_angular_velocity = arm.angular_velocity

        if muscle_on:
            arm.torque -= MUSCLE_TORQUE

        space.step(dt)

        angular_velocity = arm.angular_velocity
        angular_acceleration = (angular_velocity - previous_angular_velocity) / dt
        previous_angular_velocity = angular_velocity

        screen.fill((250, 250, 250))
        space.debug_draw(draw_options)

        shoulder = SHOULDER_POS

        dumbbell_pos = (
            int(dumbbell.position.x),
            int(dumbbell.position.y),
        )

        pygame.draw.circle(screen, (20, 20, 20), shoulder, 12)

        # 力臂 r
        pygame.draw.line(screen, (0, 70, 180), shoulder, dumbbell_pos, 4)
        pygame.draw.circle(screen, (0, 70, 180), dumbbell_pos, 6)

        # 重力箭头：永远穿过哑铃中心
        gravity_start = (dumbbell_pos[0], dumbbell_pos[1] - 70)
        gravity_end = (dumbbell_pos[0], dumbbell_pos[1] + 70)
        draw_arrow(screen, gravity_start, gravity_end, (220, 0, 0), 5)

        # 切向加速度箭头：方向由角加速度决定，长度由大小决定
        tx, ty, radius = get_tangent_vector_from_angular_acceleration(
            shoulder,
            dumbbell_pos,
            angular_acceleration,
        )

        tangential_acceleration = abs(angular_acceleration) * radius

        tangent_arrow_length = tangential_acceleration * TANGENTIAL_ARROW_SCALE
        tangent_arrow_length = clamp(
            tangent_arrow_length,
            TANGENTIAL_ARROW_MIN,
            TANGENTIAL_ARROW_MAX,
        )

        tangent_start = dumbbell_pos
        tangent_end = (
            int(dumbbell_pos[0] + tx * tangent_arrow_length),
            int(dumbbell_pos[1] + ty * tangent_arrow_length),
        )

        draw_arrow(screen, tangent_start, tangent_end, (140, 0, 200), 5)

        # 重力造成的力矩方向
        draw_arc_arrow(
            screen,
            shoulder,
            80,
            math.radians(-40),
            math.radians(80),
            (255, 140, 0),
            5,
        )

        # 肌肉反向力矩
        if muscle_on:
            draw_arc_arrow(
                screen,
                shoulder,
                115,
                math.radians(80),
                math.radians(-40),
                (0, 150, 70),
                5,
            )

        title = font.render("One-link arm torque demo", True, (0, 40, 120))
        screen.blit(title, (30, 25))

        screen.blit(
            small_font.render("Red: gravity F = mg", True, (180, 0, 0)),
            (30, 70),
        )
        screen.blit(
            small_font.render("Blue: moment arm r", True, (0, 70, 180)),
            (30, 100),
        )
        screen.blit(
            small_font.render(
                "Purple: tangential acceleration, length changes with magnitude",
                True,
                (120, 0, 180),
            ),
            (30, 130),
        )
        screen.blit(
            small_font.render("Orange: gravity torque", True, (200, 110, 0)),
            (30, 160),
        )
        screen.blit(
            small_font.render("Press M: muscle counter-torque", True, (0, 130, 60)),
            (30, 190),
        )
        screen.blit(
            small_font.render("Press R: reset", True, (60, 60, 60)),
            (30, 220),
        )

        equation = font.render("Torque: tau = r F sin(theta)", True, (20, 20, 20))
        screen.blit(equation, (600, 40))

        acc_text = small_font.render(
            f"Tangential acceleration scale: {tangential_acceleration:.1f}",
            True,
            (120, 0, 180),
        )
        screen.blit(acc_text, (600, 120))

        status_text = "Muscle torque ON" if muscle_on else "Muscle torque OFF"
        status_color = (0, 140, 60) if muscle_on else (180, 0, 0)
        screen.blit(font.render(status_text, True, status_color), (600, 80))

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()


if __name__ == "__main__":
    main()