"""
Implementation of linear algorithm to determine shape elasticity as described by Bernal et al.
"""
import numpy as np
from numba import jit, generated_jit
import shapedist.elastic_n_2
from math import floor, pi
from shapedist.comp import *
import matplotlib.pyplot as plt

@jit(nopython=True, cache=False, fastmath=True)
def running_mean(x, N):
    ret = np.zeros(x.size)
    for i in range(ret.size):
        back = i - N if (i - N) >= 0 else 0
        front = i + N if (i + N) < ret.size else ret.size - 1
        ret[i] = np.sum(x[back:front]) / (front - back)

    return ret


@jit(nopython=True, cache=False)
def get_neighborhood(tg, gamma, neigh):
    neighborhood = np.empty((tg.shape[0], 2), dtype=np.int64)
    # for i in range(tg.shape[0]-1):
    #     currd = (gamma[i + 1] - gamma[i]) / (tg[i + 1] - tg[i])
    #     if currd < 1:
    #         val = floor(1 / currd) + 1
    #         neighborhood[i][0] = min(neigh, val)
    #         neighborhood[i][1] = neigh
    #     else:
    #         val = floor(currd) + 1
    #         neighborhood[i][0] = neigh
    #         neighborhood[i][1] = min(neigh, val)
    # neighborhood[-1][0] = neigh
    # neighborhood[-1][1] = neigh
    for i in range(tg.shape[0]):
        neighborhood[i][0] = 5
        neighborhood[i][1] = 5
    return neighborhood


@jit(nopython=True, cache=False)
def find_gamma(t, p, q, parametrization_array, energy_dot, u, dim, neigh):

    # Initialize variables
    tp = t
    tq = t
    py = p
    qy = q
    n_2_precision = neigh

    initial_size = tp[parametrization_array[0]].shape[0]
    previous_n = initial_size
    parametrization_size = tp[parametrization_array[1]].shape[0]
    n = tp.size
    path = np.zeros(parametrization_size, dtype=np.float64)

    if not u:
        temp_domain_gamma = t[parametrization_array[1]]
        coarsest_domain = t[parametrization_array[0]]
    else:
        temp_domain_gamma = np.linspace(0., 1., parametrization_size)

        coarsest_domain = np.linspace(0., 1., initial_size)

    py_temp = py[parametrization_array[1]]
    qy_temp = qy[parametrization_array[1]]

    # Find coarsest solution
    current_iteration = 0

    gamma_domain, gamma_range, energy = shapedist.elastic_n_2.find_gamma(
        coarsest_domain, py[parametrization_array[0]],
        qy[parametrization_array[0]],
        n_2_precision, n_2_precision, energy_dot, u, dim)
    it = 0
    i = 0
    cont = True
    previous_path = np.zeros(parametrization_size, dtype=np.float64)

    while i < parametrization_size:
        previous_path[i], temp = interpn(temp_domain_gamma[i], gamma_domain, gamma_range, 0, previous_n, u)
        i = i + 1
    upper_ind, lower_ind  = calculate_search_area(temp_domain_gamma,
                                                     temp_domain_gamma, previous_path,
                                                     parametrization_size, u, 4)

    neighborhood_array = get_neighborhood(temp_domain_gamma, previous_path, neigh)

    path, shape_energy = iteration(temp_domain_gamma, temp_domain_gamma, py_temp, qy_temp, temp_domain_gamma, upper_ind, lower_ind,
                                       neighborhood_array, parametrization_size, energy_dot, dim, u)

    # Calculate super fine solution, if needed
    previous_n = parametrization_size
    if parametrization_array.shape[0] == 2:
        current_iteration = 1
    elif parametrization_array.shape[0] == 3:
        current_iteration = 2
        py_temp = py[parametrization_array[2]]
        qy_temp = qy[parametrization_array[2]]
        if not u:
            domain_gamma = t[parametrization_array[2]]
        else:
            domain_gamma = np.linspace(0., 1., t[parametrization_array[2]].shape[0])

        parametrization_size = domain_gamma.size
        previous_path = np.zeros(parametrization_size, dtype=np.float64)
        i = 0

        while i < parametrization_size:
            previous_path[i], temp = interpn(domain_gamma[i], temp_domain_gamma, path, 0, previous_n, u)
            i = i + 1
        neighborhood_array_final = get_neighborhood(domain_gamma, previous_path, neigh)

        upper_ind, lower_ind = calculate_search_area(domain_gamma, domain_gamma,
                                                         previous_path, parametrization_size, u, 0)

        path, shape_energy = iteration(domain_gamma, domain_gamma, py_temp, qy_temp, domain_gamma, upper_ind, lower_ind,
                                       neighborhood_array_final, parametrization_size, energy_dot, dim, u)
    return t[parametrization_array[current_iteration]], path, shape_energy


@jit(cache=False, nopython=True)
def calculate_search_area(new_domain, prev_domain, prev_path, parametrization_size, u, it):
    # strip_height = max(new_domain.shape[0] / (prev_domain.shape[0] * np.sqrt(2) / 2) + 3 + it * 2, 8)
    strip_height = 8
    # strip_height = 2 * it + 4
    upper_bound_temp = np.zeros((prev_domain.size, 2), dtype=np.float64)
    lower_bound_temp = np.zeros((prev_domain.size, 2), dtype=np.float64)
    upper_bound_temp[:, 0] = prev_domain
    upper_bound_temp[:, 1] = prev_path
    lower_bound_temp[:, 0] = prev_domain
    lower_bound_temp[:, 1] = prev_path
    theta = pi / 4
    rotation_matrix = np.array(((np.cos(theta), -np.sin(theta)), (np.sin(theta), np.cos(theta))))
    unit_up = np.zeros(2, np.float64)
    unit_up[1] = 1

    upper_bound_temp = upper_bound_temp + (rotation_matrix @ unit_up) * strip_height / parametrization_size
    lower_bound_temp = lower_bound_temp - (rotation_matrix @ unit_up) * strip_height / parametrization_size

    upper_bound = np.zeros(parametrization_size, dtype=np.float64)
    lower_bound = np.zeros(parametrization_size, dtype=np.float64)

    for i in range(parametrization_size):
        if new_domain[i] > upper_bound_temp[-1, 0]:
            upper_bound[i] = 1
        else:
            upper_bound[i], temp = interpn(new_domain[i], upper_bound_temp[:, 0], upper_bound_temp[:, 1], 0,
                                          parametrization_size, u)
    for i in range(parametrization_size):
        if new_domain[i] < lower_bound_temp[0, 0]:
            lower_bound[i] = 0
        else:
            lower_bound[i], temp = interpn(new_domain[i], lower_bound_temp[:, 0], lower_bound_temp[:, 1], 0,
                                          parametrization_size, u)

    upper_bound = running_mean(upper_bound, 6)
    lower_bound = running_mean(lower_bound, 6)
    upper_ind = np.empty(upper_bound.shape, dtype=np.int64)
    lower_ind = np.empty(lower_bound.shape, dtype=np.int64)
    p1 = 0
    p2 = 0
    N = upper_ind.shape[0]
    for i in range(N):
        upper_ind[i] = search(upper_bound[i], new_domain, p1, N)
        lower_ind[i] = search(lower_bound[i], new_domain, p2, N)
        p1 = upper_ind[i]
        p2 = lower_ind[i]

    return upper_ind, lower_ind

@jit(cache=False, nopython=True)
def search(t, x, lower, upper):
    i = 0
    while lower < upper:
        i = lower + (upper - lower) // 2
        val = x[i]
        if t == val:
            break
        elif t > val:
            if lower == i:
                break
            lower = i
        elif t < val:
            upper = i
    return i

@jit(cache=False, nopython=True)
def iteration(tp_temp, tq_temp, py_temp, qy_temp, temp_domain_gamma, upper_ind, lower_ind,
              neighborhood_array, parametrization_size, energy_dot, dim, u):
    # Linear Iteration
    start = np.empty(dim, dtype=np.int64)
    val1 = np.empty(dim, dtype=np.float64)
    end = np.empty(dim, dtype=np.int64)
    val2 = np.empty(dim, dtype=np.float64)
    path = np.zeros(parametrization_size, dtype=np.float64)
    gamma = tp_temp
    m = parametrization_size
    n = parametrization_size

    min_energy_values = np.full((n, n), np.inf, dtype=np.float64)
    path_nodes = np.zeros((n, n, 2), dtype=np.int64)
    j = 1
    while j < upper_ind[1] and j < 6:
        min_energy_values[1][j] = integrate(tp_temp, tp_temp, py_temp, qy_temp, 0, 1, 0, j, gamma, energy_dot,
                                                dim, start, end, val1, val2, u)
        j = j + 1
    i = 1
    j = 1
    while lower_ind[i] < j and i < 6:
        min_energy_values[i][1] = integrate(tp_temp, tp_temp, py_temp, qy_temp, 0, i, 0, 1, gamma, energy_dot,
                                                dim, start, end, val1, val2, u)
        i = i + 1
    i, j, k, l = 1, 1, 1, 1

    while i < n - 1:
        j = max(1, lower_ind[i])
        while j < m - 1 and j <= upper_ind[i]:
            points_considered = 0
            toconsider = neighborhood_array[i][0] * neighborhood_array[i][1]
            k = i-1
            minimum = min_energy_values[i][j]
            while k > 0 and points_considered < toconsider:
                l = min(upper_ind[k], j-1)
                te = 0
                while l > 0 and l > lower_ind[k] and te < neighborhood_array[i][1]:
                    e = min_energy_values[k, l] + integrate(tp_temp, tq_temp, py_temp, qy_temp,
                                                            k, i, l, j,
                                                            gamma, energy_dot,
                                                            dim, start, end, val1, val2, u)
                    if e <= minimum:
                        minimum = e
                        path_nodes[i][j][0] = k
                        path_nodes[i][j][1] = l
                    points_considered = points_considered + 1
                    te = te + 1
                    l = l - 1
                k = k - 1
            min_energy_values[i][j] = minimum
            j = j + 1
        i = i + 1
    i = n - 1
    j = m - 1

    # k = i - neighborhood_array[i][0]
    # if k <= 0:
    #     k = 1
    # minimum = min_energy_values[i][j]
    # while k < i:
    #     l = j - neighborhood_array[i][1]
    #     if l>= lower_ind[i]:
    #         if l <= 0:
    #             l = 1
    #         while l < j and l < upper_ind[k]:
    #             e = min_energy_values[k, l] + integrate(tp_temp, tq_temp, py_temp, qy_temp,
    #                                                     k, i, l, j,
    #                                                     gamma, energy_dot,
    #                                                     dim, start, end, val1, val2, u)
    #             if e < minimum:
    #                 minimum = e
    #                 path_nodes[i][j][0] = k
    #                 path_nodes[i][j][1] = l
    #
    #             l = l + 1
    #     k = k + 1
    # min_energy_values[i][j] = minimum
    points_considered = 0
    toconsider = neighborhood_array[i][0] * neighborhood_array[i][1]
    k = i - 1
    minimum = min_energy_values[i][j]
    while k > 0 and points_considered < toconsider:
        l = min(upper_ind[k], j - 1)
        te = 0
        while l > 0 and l > lower_ind[k] and te < neighborhood_array[i][1]:
            e = min_energy_values[k, l] + integrate(tp_temp, tq_temp, py_temp, qy_temp,
                                                    k, i, l, j,
                                                    gamma, energy_dot,
                                                    dim, start, end, val1, val2, u)
            if e <= minimum:
                minimum = e
                path_nodes[i][j][0] = k
                path_nodes[i][j][1] = l
            points_considered = points_considered + 1
            te = te + 1
            l = l - 1
        k = k - 1
    min_energy_values[i][j] = minimum

    # !! Interpolate
    path_indices = np.zeros((n, 2), dtype=np.int64)
    path_indices[0][0] = n - 1
    path_indices[0][1] = m - 1

    i = 0
    while path_indices[i][0] != 0 or path_indices[i][1] != 0 and i + 1 < path.size:
        result = path_nodes[path_indices[i][0]][path_indices[i][1]]
        path_indices[i + 1][0] = result[0]
        path_indices[i + 1][1] = result[1]
        i = i + 1
    i = 0
    previous = 1
    previousIndex_domain = n - 1
    previousIndex_gamma = n - 1
    t = gamma
    path[path_indices[0][0]] = gamma[path_indices[0][1]]
    while i < path_indices.size // 2 and previousIndex_domain != 0:
        path[path_indices[i][0]] = gamma[path_indices[i][1]]
        if previousIndex_domain - path_indices[i][0] > 1:
            j = 0
            val = (gamma[previousIndex_gamma] - gamma[path_indices[i][1]]) / \
                  (t[previousIndex_domain] - t[path_indices[i][0]])
            while j < previousIndex_domain - path_indices[i][0]:
                path[previousIndex_domain - j] = previous - (t[previousIndex_domain] -
                                                             t[previousIndex_domain - j]) * val

                j = j + 1
        previousIndex_domain = path_indices[i][0]
        previousIndex_gamma = path_indices[i][1]
        previous = gamma[path_indices[i][1]]
        i = i + 1
    return path, min_energy_values[n - 1][m - 1]
