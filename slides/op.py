import numpy as np
from scipy.optimize import minimize

tau = 20

def objective(F):
    F1, F2, F3 = F
    return F1**2 + F2**2 + F3**2

def constraint(F):
    F1, F2, F3 = F
    return 2*F1 + 3*F2 + 5*F3 - tau

step = 0

def callback(F):
    global step
    step += 1
    F1, F2, F3 = F
    print(f"step {step}: F1={F1:.6f}, F2={F2:.6f}, F3={F3:.6f}")

constraints = {
    "type": "eq",
    "fun": constraint
}

initial_guess = np.array([100.0, 100.0, 100.0])

result = minimize(
    objective,
    initial_guess,
    method="SLSQP",
    constraints=constraints,
    callback=callback,
    options={"disp": True, "maxiter": 100}
)

print("\nFinal result:")
print("F1 =", result.x[0])
print("F2 =", result.x[1])
print("F3 =", result.x[2])
print("objective =", result.fun)
print("constraint value =", 2*result.x[0] + 3*result.x[1] + 5*result.x[2])