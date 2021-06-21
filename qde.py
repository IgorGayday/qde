"""This module contains functions that solve differential equations by transforming them to QUBO problems, which allows solution on quantum annealer.
"""
import findiff
import numpy as np
from dwave_qbsolv import QBSolv


def build_quadratic_minimization_matrix(npoints, dx):
    """Builds a matrix that defines quadratic minimization problem (H) corresponding to a given 1st order differential equation using 1st order forward difference scheme.

    Args:
        npoints (int): Number of discretization points for functions defining a given problem.
        dx (float): Grid step.

    Returns:
        numpy.ndarray (2D): Quadratic minimization matrix.
    """
    H = np.diag([2] * (npoints - 1)) + np.diag([-1] * (npoints - 2), 1) + np.diag([-1] * (npoints - 2), -1)
    H[-1, -1] = 1
    return H / dx ** 2


def get_finite_difference_coefficients(deriv_order, accuracy_order):
    """Returns coefficients of a given forward finite difference scheme.

    Args:
        deriv_order (int): Order of derivative.
        accuracy_order (int): Order of accuracy.

    Returns:
        numpy.ndarray (1D): Coefficients of selected scheme.
    """
    if deriv_order == 0:
        return np.array([1])

    elif accuracy_order % 2 == 0:
        ans = findiff.coefficients(deriv_order, accuracy_order)['forward']
        return ans['coefficients']

    else:
        coeffs = None
        if accuracy_order == 1:
            if deriv_order == 1:
                coeffs = np.array([-1, 1])
            elif deriv_order == 2:
                coeffs = np.array([1, -2, 1])

        elif accuracy_order == 3:
            if deriv_order == 1:
                coeffs = np.array([-11/6, 3, -3/2, 1/3])

        elif accuracy_order == 5:
            if deriv_order == 1:
                coeffs = np.array([-137/60, 5, -5, 10/3, -5/4, 1/5])

        if coeffs is None:
            raise NotImplementedError('Not implemented combination of derivative and accuracy orders')
        else:
            return coeffs


def get_deriv_range(deriv_ind, point_ind, last_point_ind, max_considered_accuracy):
    """Returns derivative order, accuracy order, shift and first point index of a given derivative term.

    Args:
        deriv_ind (int): Index of term in DE equation.
        point_ind (int): Global index of point for which derivative range is requested.
        last_point_ind (int): Maximum global point index eligible to be included in a given scheme.
        max_considered_accuracy (int): Maximum considered accuracy order for a finite difference scheme.

    Returns:
        deriv_order (int): Derivative order of this term.
        selected_accuracy (int): Selected accuracy order for this term. If <1, then the remaining return values are invalid.
        length (int): Number of points in the selected scheme.
        last_scheme_ind_global (int): Global index of the last point in the selected scheme.
    """
    deriv_order = deriv_ind - 1
    if deriv_order == 0:
        selected_accuracy = 1
    else:
        max_possible_accuracy = last_point_ind - point_ind - deriv_order + 1
        selected_accuracy = min(max_considered_accuracy, max_possible_accuracy)

    length = deriv_order + selected_accuracy
    last_scheme_ind_global = point_ind + length - 1
    return deriv_order, selected_accuracy, length, last_scheme_ind_global


def add_linear_terms(d, point_ind, last_unknown_ind_global, funcs, dx, known_points, max_considered_accuracy):
    """Adds linear matrix elements resulting from linear terms of error functional for a given point.

    Args:
        d (numpy.ndarray (1D)): Current quadratic minimization vector to which linear matrix elements of specified point are added.
        point_ind (int): Global index of point for which the terms are to be calculated.
        last_unknown_ind_global (int): Global index of the last unknown variable included in a given calculation.
        funcs (numpy.ndarray (2D)): Matrix with values of DE shift and multiplier functions. See `build_quadratic_minimization_matrices_general` for more details.
        dx (float): Grid step.
        known_points (numpy.ndarray (1D)): Array of known points in solution (continuous from the left end).
        max_considered_accuracy (int): Maximum accuracy order of finite difference scheme. Lower order is automatically used is number of points is not sufficient.
    """
    first_unknown_ind_global = known_points.shape[0]
    for deriv_ind in range(1, funcs.shape[0]):
        deriv_order, accuracy_order, length, last_scheme_ind_global = get_deriv_range(deriv_ind, point_ind, last_unknown_ind_global, max_considered_accuracy)
        if last_scheme_ind_global < first_unknown_ind_global or accuracy_order < 1:
            continue
        coeffs = get_finite_difference_coefficients(deriv_order, accuracy_order)
        func_factor = 2 * funcs[0, point_ind] * funcs[deriv_ind, point_ind] / dx ** deriv_order
        for scheme_ind in range(length):
            unknown_ind = point_ind + scheme_ind - first_unknown_ind_global
            if unknown_ind < 0:
                continue
            else:
                d[unknown_ind] += func_factor * coeffs[scheme_ind]


def add_quadratic_terms(H, d, point_ind, last_unknown_ind_global, funcs, dx, known_points, max_considered_accuracy):
    """Adds linear and quadratic matrix elements resulting from quadratic terms of error functional for a given point.

    Args:
        H (numpy.ndarray (2D)): Current quadratic minimization matrix to which quadratic matrix elements of specified point are added.
        d (numpy.ndarray (1D)): Current quadratic minimization vector to which linear matrix elements of specified point are added.
        point_ind (int): Global index of point for which the terms are to be calculated.
        last_unknown_ind_global (int): Global index of the last unknown variable included in a given calculation.
        funcs (numpy.ndarray (2D)): Matrix with values of DE shift and multiplier functions. See `build_quadratic_minimization_matrices_general` for more details.
        dx (float): Grid step.
        known_points (numpy.ndarray (1D)): Array of known points in solution (continuous from the left end).
        max_considered_accuracy (int): Maximum accuracy order of finite difference scheme. Lower order is automatically used is number of points is not sufficient.
    """
    first_unknown_index_global = known_points.shape[0]
    for deriv_ind1 in range(1, funcs.shape[0]):
        deriv_order1, accuracy_order1, length1, last_scheme_ind_global1 = get_deriv_range(deriv_ind1, point_ind, last_unknown_ind_global, max_considered_accuracy)
        if accuracy_order1 < 1:
            continue
        coeffs1 = get_finite_difference_coefficients(deriv_order1, accuracy_order1)
        for deriv_ind2 in range(1, funcs.shape[0]):
            deriv_order2, accuracy_order2, length2, last_scheme_ind_global2 = get_deriv_range(deriv_ind2, point_ind, last_unknown_ind_global, max_considered_accuracy)
            if last_scheme_ind_global1 < first_unknown_ind_global and last_scheme_ind_global2 < first_unknown_ind_global or accuracy_order2 < 1:
                continue
            coeffs2 = get_finite_difference_coefficients(deriv_order2, accuracy_order2)
            func_factor = funcs[deriv_ind1, point_ind] * funcs[deriv_ind2, point_ind] / dx ** (deriv_order1 + deriv_order2)
            for scheme_ind1 in range(length1):
                unknown_ind1 = point_ind + scheme_ind1 - first_unknown_ind_global
                for scheme_ind2 in range(length2):
                    unknown_ind2 = point_ind + scheme_ind2 - first_unknown_ind_global
                    if unknown_ind1 < 0 and unknown_ind2 < 0:
                        continue
                    else:
                        h_factor = func_factor * coeffs1[scheme_ind1] * coeffs2[scheme_ind2]
                        if unknown_ind1 >= 0 and unknown_ind2 >= 0:
                            H[unknown_ind1, unknown_ind2] += h_factor
                        else:
                            unknown_ind = max(unknown_ind1, unknown_ind2)
                            known_ind = min(unknown_ind1, unknown_ind2) + first_unknown_ind_global
                            d[unknown_ind] += h_factor * known_points[known_ind]


def build_quadratic_minimization_matrices_general(funcs, dx, known_points, max_considered_accuracy=1, points_per_step=1, **kwargs):
    """Builds a matrix that defines quadratic minimization problem (H) corresponding to a given n-th order differential equation using k-th order (even) difference schemes.

    Args:
        funcs (numpy.ndarray (2D)): Matrix with values of DE shift and multiplier functions. Functions are stored in rows. First row stores f (shift function).
            Subsequent i-th row stores f_(i-1) (multiplier function of (i-1)-th derivative term). Number of columns is equal to number of function discretization points.
        dx (float): Grid step.
        known_points (numpy.ndarray (1D)): Array of known points in solution (continuous from the left end).
        max_considered_accuracy (int): Maximum accuracy order of finite difference scheme. Lower order is automatically used is number of points is not sufficient.
        points_per_step (int): Number of points to vary in the problem, defined by this matrix.

    Returns:
        H (numpy.ndarray (2D)): Quadratic minimization matrix.
        d (numpy.ndarray (1D)): Quadratic minimization vector.
    """
    first_unknown_ind_global = known_points.shape[0]
    unknowns = min(points_per_step, funcs.shape[1] - first_unknown_ind_global)
    last_unknown_ind_global = first_unknown_ind_global + unknowns - 1
    H = np.zeros((unknowns, unknowns))
    d = np.zeros(unknowns)
    for point_ind in range(last_unknown_ind_global + 1):
        add_linear_terms(d, point_ind, last_unknown_ind_global, funcs, dx, known_points, max_considered_accuracy)
        add_quadratic_terms(H, d, point_ind, last_unknown_ind_global, funcs, dx, known_points, max_considered_accuracy)
    return H, d


def build_quadratic_minimization_vector(f, dx, y1):
    """Builds a vector that defines quadratic minimization problem (d) corresponding to a given differential equation.

    Args:
        f (numpy.ndarray (1D)): Array of values of the derivative at the grid points.
        dx (float): Grid step.
        y1 (float): Solution's value at the leftmost point (boundary condition).

    Returns:
        numpy.ndarray (1D): Quadratic minimization vector.
    """
    d = -f[0:-1]
    d[0:-1] += f[1:-1]
    d[0] -= y1 / dx
    return d * 2 / dx


def build_discretization_matrix(qbits_integer, qbits_decimal):
    """Builds a discretization matrix (H~) for given number of qubits in integer and decimal parts.

    Args:
        qbits_integer (int): Number of qubits to represent integer part of each expansion coefficient (value) of the sample solution.
        qbits_decimal (int): Number of qubits to represent decimal part of each expansion coefficient.

    Returns:
        numpy.ndarray (2D): Discretization matrix.
    """
    j_range = range(-qbits_integer + 1, qbits_decimal + 1)
    return np.reshape([2 ** -(j1 + j2) for j1 in j_range for j2 in j_range], (len(j_range), len(j_range)))


def build_discretization_vector(qbits_integer, qbits_decimal):
    """Builds a discretization vector (d~) for given number of qubits in integer and decimal parts.

    Args:
        qbits_integer (int): Number of qubits to represent integer part of each expansion coefficient (value) of the sample solution.
        qbits_decimal (int): Number of qubits to represent decimal part of each expansion coefficient.

    Returns:
        numpy.ndarray (1D): Discretization vector.
    """
    j_range = range(-qbits_integer + 1, qbits_decimal + 1)
    return np.array([2 ** -j for j in j_range])


def build_qubo_matrix(f, dx, y1, H_discret_elem, d_discret_elem, signed):
    """Builds a QUBO matrix (Q) corresponding to a given differential equation. 

    A sample solution is represented by its values at grid points discretized using fixed point representation with set number of qubits.
    Derivative at each point of sample solution is calculated with a finite difference method and compared with the true derivative f.
    Sum of squares of their difference at all points of the sample solutions constitutes the target functional.

    Args:
        f (numpy.ndarray (1D)): Array of values of the derivative at the grid points.
        dx (float): Grid step.
        y1 (float): Solution's value at the leftmost point (boundary condition).
        H_discret_elem (numpy.ndarray (2D)): Matrix discretization element for given number of qubits (see also build_discretization_matrix).
        d_discret_elem (numpy.ndarray (1D)): Vector discretization element for given number of qubits (see also build_discretization_vector).
        signed (bool): Whether to use signed or unsigned number representation. Using signed numbers shifts representation range from 0..L to -L/2..L/2, where L = 2 ** qbits_integer.

    Returns:
        Q (numpy.ndarray): QUBO matrix.
    """
    H_cont = build_quadratic_minimization_matrix(len(f), dx)
    d_cont = build_quadratic_minimization_vector(f, dx, y1)
    if signed:
        d_cont[0] -= 2 * d_discret_elem[0] / dx ** 2

    H_bin = np.block([[H_discret_elem * val for val in row] for row in H_cont])
    d_bin = np.block([d_discret_elem * val for val in d_cont])
    Q = H_bin + np.diag(d_bin)
    return Q


def solve(f, dx, y1, qbits_integer, qbits_decimal, signed=True, points_per_qubo=1, average_solutions=False, **kwargs):
    """Solves a given differential equation, defined by f and y1, by formulating it as a QUBO problem with given discretization precision.

    Args:
        f (numpy.ndarray (1D)): Array of values of the derivative at the grid points.
        dx (float): Grid step.
        y1 (float): Solution's value at the leftmost point (boundary condition).
        qbits_integer (int): Number of qubits to represent integer part of each expansion coefficient (value) of the sample solution.
        qbits_decimal (int): Number of qubits to represent decimal part of each expansion coefficient.
        signed (bool): Whether to use signed or unsigned number representation. Using signed numbers shifts representation range from 0..L to -L/2..L/2, where L = 2 ** qbits_integer.
        points_per_qubo (int): Number of points to propagate in each QUBO. Last point from the previous solution is used as boundary condition for the next solution.
        average_solutions (bool): If true, all found solutions are averaged according to number of times they were found. If false, only the best solution is considered.
        kwargs (dict): Additional keyword arguments to QBSolv().sample_qubo

    Returns:
        numpy.ndarray (2D): Values of the best found solution function at grid points.
    """
    solution = np.empty(len(f))
    solution[0] = y1

    H_discret_elem = build_discretization_matrix(qbits_integer, qbits_decimal)
    d_discret_elem = build_discretization_vector(qbits_integer, qbits_decimal)
    error = 0
    for i in range(1, len(f), points_per_qubo):
        y1 = solution[i - 1]
        next_i = min(i + points_per_qubo, len(f))
        next_f = f[i - 1 : next_i]
        Q = build_qubo_matrix(next_f, dx, y1, H_discret_elem, d_discret_elem, signed)
        sample_set = QBSolv().sample_qubo(Q, **kwargs)
        samples_bin = np.array([list(sample.values()) for sample in sample_set])
        samples_bin_structured = samples_bin.reshape((samples_bin.shape[0], -1, len(d_discret_elem)))
        samples_cont = np.sum(samples_bin_structured * d_discret_elem, 2)
        error_shift = (y1 ** 2 + 2 * y1 * next_f[0] * dx) / dx ** 2 + np.sum(next_f[0:-1] ** 2)
        if signed:
            samples_cont -= 2 ** (qbits_integer - 1)
            error_shift += (4 ** (qbits_integer - 1) + 2 ** qbits_integer * (y1 + next_f[0] * dx)) / dx ** 2

        if average_solutions:
            num_occurrences = np.array([sample.num_occurrences for sample in sample_set.data()])
            weights = num_occurrences / np.sum(num_occurrences)
            solution[i:next_i] = np.sum(samples_cont * weights[:, np.newaxis], 0)
            all_energies = np.array([sample.energy for sample in sample_set.data()])
            solution_energy = np.sum(all_energies * weights)
        else:
            solution[i:next_i] = samples_cont[0, :]
            solution_energy = next(sample_set.data()).energy

        error += solution_energy + error_shift

    return solution, error
