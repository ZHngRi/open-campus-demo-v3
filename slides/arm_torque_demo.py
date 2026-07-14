import math
import pygame
import pymunk
import pymunk.pygame_util


WIDTH, HEIGHT = 1100, 1000
FPS = 60

GRAVITY = 900
SHOULDER_POS = (500, 420)

UPPER_ARM_LENGTH = 210
FOREARM_LENGTH = 260
ARM_THICKNESS = 18

FOREARM_MASS = 1.8
DUMBBELL_MASS = 8.0

ELBOW_MOTOR_RATE = -2.5
ELBOW_MOTOR_FORCE = 1_200_000

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


def create_fixed_upper_arm(space):
    shoulder = SHOULDER_POS
    elbow = (SHOULDER_POS[0], SHOULDER_POS[1] + UPPER_ARM_LENGTH)

    shape = pymunk.Segment(space.static_body, shoulder, elbow, ARM_THICKNESS / 2)
    shape.color = pygame.Color(220, 175, 120, 255)
    shape.friction = 0.8

    space.add(shape)
    return elbow


def create_forearm(space, elbow_pos):
    moment = pymunk.moment_for_box(FOREARM_MASS, (FOREARM_LENGTH, ARM_THICKNESS))
    body = pymunk.Body(FOREARM_MASS, moment)

    body.position = (elbow_pos[0] + FOREARM_LENGTH / 2, elbow_pos[1])
    body.angle = 0

    shape = pymunk.Poly.create_box(body, (FOREARM_LENGTH, ARM_THICKNESS))
    shape.color = pygame.Color(220, 175, 120, 255)
    shape.friction = 0.8

    elbow_joint = pymunk.PivotJoint(
        space.static_body,
        body,
        elbow_pos,
        (-FOREARM_LENGTH / 2, 0),
    )
    elbow_joint.collide_bodies = False

    elbow_motor = pymunk.SimpleMotor(space.static_body, body, 0.0)
    elbow_motor.max_force = HOLD_MOTOR_FORCE

    space.add(body, shape, elbow_joint, elbow_motor)

    return body, elbow_motor


def create_dumbbell(space, forearm):
    hand_pos = forearm.local_to_world((FOREARM_LENGTH / 2, 0))

    moment = pymunk.moment_for_circle(DUMBBELL_MASS, 0, 34)
    body = pymunk.Body(DUMBBELL_MASS, moment)
    body.position = hand_pos

    shape = pymunk.Circle(body, 34)
    shape.color = pygame.Color(45, 45, 45, 255)
    shape.friction = 0.8

    joint = pymunk.PinJoint(
        forearm,
        body,
        (FOREARM_LENGTH / 2, 0),
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

    elbow_pos = create_fixed_upper_arm(space)
    forearm, elbow_motor = create_forearm(space, elbow_pos)
    dumbbell = create_dumbbell(space, forearm)

    return elbow_pos, forearm, dumbbell, elbow_motor


def main():
    pygame.init()

    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Fixed Upper Arm Two-Link Demo")

    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Arial", 24)
    small_font = pygame.font.SysFont("Arial", 20)

    space = pymunk.Space()
    space.gravity = (0, GRAVITY)

    draw_options = pymunk.pygame_util.DrawOptions(screen)

    elbow_pos, forearm, dumbbell, elbow_motor = reset(space)

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
                    elbow_pos, forearm, dumbbell, elbow_motor = reset(space)
                    gravity_mode = False
                    motor_on = False

        if gravity_mode:
            if motor_on:
                elbow_motor.rate = ELBOW_MOTOR_RATE
                elbow_motor.max_force = ELBOW_MOTOR_FORCE
            else:
                elbow_motor.rate = 0.0
                elbow_motor.max_force = 0.0
        else:
            elbow_motor.rate = 0.0
            elbow_motor.max_force = HOLD_MOTOR_FORCE
            forearm.angular_velocity = 0.0
            forearm.angle = 0.0

        space.step(dt)

        screen.fill((255, 255, 255))
        space.debug_draw(draw_options)

        shoulder = SHOULDER_POS
        elbow_i = (int(elbow_pos[0]), int(elbow_pos[1]))
        hand_i = endpoint(forearm, FOREARM_LENGTH / 2)
        dumbbell_pos = (int(dumbbell.position.x), int(dumbbell.position.y))

        pygame.draw.circle(screen, (20, 20, 20), shoulder, 11)
        pygame.draw.circle(screen, (20, 20, 20), elbow_i, 10)
        pygame.draw.circle(screen, (20, 20, 20), hand_i, 7)

        pygame.draw.line(screen, (0, 80, 190), elbow_i, dumbbell_pos, 4)

        gravity_start = (dumbbell_pos[0], dumbbell_pos[1] - 75)
        gravity_end = (dumbbell_pos[0], dumbbell_pos[1] + 75)
        draw_arrow(screen, gravity_start, gravity_end, (220, 0, 0), 5)

        title = font.render("Fixed upper arm + controllable forearm", True, (0, 40, 120))
        screen.blit(title, (30, 30))

        screen.blit(small_font.render("G: switch HOLD / GRAVITY", True, (20, 20, 20)), (30, 75))
        screen.blit(small_font.render("B: elbow motor on/off", True, (0, 120, 60)), (30, 105))
        screen.blit(small_font.render("R: reset", True, (60, 60, 60)), (30, 135))

        mode_text = "Mode: GRAVITY" if gravity_mode else "Mode: HOLD"
        mode_color = (180, 0, 0) if gravity_mode else (0, 120, 60)
        screen.blit(font.render(mode_text, True, mode_color), (760, 40))

        motor_text = "Elbow motor ON" if motor_on else "Elbow motor OFF"
        motor_color = (0, 140, 60) if motor_on else (120, 120, 120)
        screen.blit(font.render(motor_text, True, motor_color), (760, 80))

        screen.blit(
            small_font.render("Red: dumbbell weight F = mg", True, (180, 0, 0)),
            (30, 175),
        )
        screen.blit(
            small_font.render("Blue: moment arm from elbow to dumbbell", True, (0, 80, 190)),
            (30, 205),
        )

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()


if __name__ == "__main__":
    main()