import random
import re
from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from owlready2 import get_ontology

app = Flask(__name__)
app.secret_key = "supersecretkey"  # Needed for storing user session data (quiz data, etc.)

# Load the ontology
ontology_path = "ontology/math_area_its.owl"
onto = get_ontology("file://" + ontology_path).load()

# ------------- Utility Functions -------------
def parse_formula(formula_str):
    """
    Parse the formula string from the ontology to something we can evaluate.
    We'll transform '^2' into '**2' for Python and handle multiplication.
    """
    formula_str = re.sub(r'(\w+)\^2', r'(\1**2)', formula_str)
    return formula_str.strip()

def evaluate_area(formula_str, **kwargs):
    """
    Evaluate the formula string by substituting the given variables (kwargs).
    E.g., "0.5 * base * height" with base=10, height=5 => 25.0
    """
    local_dict = {k: float(v) for k, v in kwargs.items()}
    parsed = parse_formula(formula_str)
    try:
        result = eval(parsed, {"__builtins__": None}, local_dict)
    except:
        result = None
    return result

def get_all_shapes():
    """Retrieve all shape individuals from the ontology with their data."""
    shapes = []
    for indiv in onto.individuals():
        # Check if the individual is a Shape or a descendant
        if any(onto.Shape in cls.ancestors() for cls in indiv.is_a):
            shape_info = {}
            shape_info["name"] = indiv.name  # e.g., "TriangleInstance"
            shape_info["description"] = (indiv.description[0] 
                                         if hasattr(indiv, 'description') 
                                            and indiv.description 
                                         else "")
            if hasattr(indiv, 'hasFormula') and indiv.hasFormula:
                formula_obj = indiv.hasFormula[0]
                shape_info["formula_str"] = (formula_obj.formulaExpression[0] 
                                             if hasattr(formula_obj, 'formulaExpression') 
                                                and formula_obj.formulaExpression 
                                             else "")
            else:
                shape_info["formula_str"] = ""
            # Derive a user-friendly label from the name, e.g. "TriangleInstance" -> "Triangle"
            shape_info["label"] = shape_info["name"].replace("Instance", "")
            
            # Derive an image filename from the label (all lowercase)
            shape_info["image_file"] = shape_info["label"].lower() + ".png"
            
            shapes.append(shape_info)
    return shapes

def get_random_dimensions(shape_label):
    """
    Generate random dimension values for the given shape
    by scanning the shape's formula for known variables.
    """
    shapes = get_all_shapes()
    shape_data = next((s for s in shapes if s["name"] == shape_label), None)
    if not shape_data:
        return None
    
    formula_str = shape_data["formula_str"]
    possible_vars = ["base", "height", "side", "length", "width", "radius", "base1", "base2"]
    used_vars = [v for v in possible_vars if v in formula_str]
    
    random_dims = {}
    for var in used_vars:
        random_dims[var] = round(random.uniform(1, 15), 2)
    return random_dims

# ------------- Routes -------------
@app.route("/")
def index():
    """Home page showing the overview of shapes and links to quizzes."""
    shapes = get_all_shapes()
    return render_template("index.html", shapes=shapes)

@app.route("/shape/<shape_name>", methods=["GET", "POST"])
def shape_detail(shape_name):
    """
    Detailed page for a single shape. The user can input values and guess an area.
    We compare with the correct area and give feedback.
    """
    shapes = get_all_shapes()
    shape_data = next((s for s in shapes if s["name"] == shape_name), None)
    if not shape_data:
        return "Shape not found", 404
    
    result_message = None
    is_correct = None  
    user_area = None
    system_area = None
    
    if request.method == "POST":
        # Figure out what variables the formula needs
        formula_str = shape_data["formula_str"]
        parsed = parse_formula(formula_str)
        
        possible_vars = ["base", "height", "side", "length", "width", "radius", "base1", "base2"]
        used_vars = [v for v in possible_vars if v in formula_str]
        
        # Build dictionary from form
        input_vars = {}
        for var in used_vars:
            user_val = request.form.get(var, None)
            if user_val is not None:
                try:
                    input_vars[var] = float(user_val)
                except ValueError:
                    input_vars[var] = 0.0
        
        # Evaluate system's area
        system_area = evaluate_area(formula_str, **input_vars)
        
        # Compare with user area guess
        user_area_str = request.form.get("area", None)
        if user_area_str:
            try:
                user_area = float(user_area_str)
                # Tolerance check
                if abs(user_area - system_area) < 0.0001:
                    result_message = "Correct! Great job."
                    is_correct = True
                else:
                    # Show correct area to 1 decimal place
                    result_message = f"Incorrect. The correct area is {round(system_area, 1)}."
                    is_correct = False
            except ValueError:
                user_area = None
                result_message = "Please enter a valid numeric area."
                is_correct = False
        else:
            # If user didn't guess, just show the system's area
            result_message = f"The area for the given dimensions is {round(system_area, 1)}."
            is_correct = None
    
    return render_template(
        "shape_detail.html", 
        shape=shape_data,
        result_message=result_message,
        is_correct=is_correct,
        user_area=user_area,
        system_area=system_area
    )

@app.route("/quiz")
def quiz():
    """
    A quiz page that randomly selects a shape and dimensions.
    User tries to guess the area. We'll store the info in session for checking.
    """
    shapes = get_all_shapes()
    chosen_shape = random.choice(shapes)
    dims = get_random_dimensions(chosen_shape["name"])
    
    # Evaluate the area
    raw_area = evaluate_area(chosen_shape["formula_str"], **dims)
    
    # Round the correct area to 1 decimal place BEFORE storing
    correct_area = round(raw_area, 1)
    
    session["quiz_data"] = {
        "shape_name": chosen_shape["name"],
        "dims": dims,
        "correct_area": correct_area
    }
    
    return render_template("quiz.html", shape=chosen_shape, dims=dims)

@app.route("/quiz-check", methods=["POST"])
def quiz_check():
    quiz_data = session.get("quiz_data", {})
    if not quiz_data:
        return redirect(url_for("quiz"))
    
    user_guess_str = request.form.get("area_guess")
    if not user_guess_str:
        return redirect(url_for("quiz"))
    
    try:
        user_guess = float(user_guess_str)
    except ValueError:
        return redirect(url_for("quiz"))
    
    correct_area = quiz_data.get("correct_area", 0.0)
    shape_name = quiz_data.get("shape_name")
    dims = quiz_data.get("dims", {})

    if abs(user_guess - correct_area) < 0.0001:
        result_message = "Correct! Excellent work!"
        is_correct = True
    else:
        result_message = f"Incorrect. The correct area is {correct_area}"
        is_correct = False
    
    shape_data = next((s for s in get_all_shapes() if s["name"] == shape_name), None)
    return render_template(
        "quiz.html",
        shape=shape_data,
        dims=dims,
        user_guess=user_guess,
        correct_area=correct_area,
        result_message=result_message,
        is_correct=is_correct
    )

if __name__ == "__main__":
    app.run(debug=True)
