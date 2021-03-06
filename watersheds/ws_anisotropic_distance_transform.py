import vigra
import numpy as np
from wsdt import group_seeds_by_distance, iterative_inplace_watershed


def signed_anisotropic_dt(
        pmap,
        threshold,
        anisotropy,
        preserve_membrane_pmaps
        ):

    binary_membranes = (pmap >= threshold).astype('uint32')
    distance_to_membrane = vigra.filters.distanceTransform(
            binary_membranes,
            pixel_pitch = [anisotropy, 1., 1.])

    if preserve_membrane_pmaps:
        # Instead of computing a negative distance transform within the thresholded membrane areas,
        # Use the original probabilities (but inverted)
        membrane_mask = binary_membranes.astype(np.bool)
        distance_to_membrane[membrane_mask] = -pmap[membrane_mask]
    else:
        # Save RAM with a sneaky trick:
        # Use distanceTransform in-place, despite the fact that the input and output don't have the same types!
        # (We can just cast labeled as a float32, since uint32 and float32 are the same size.)
        distance_to_nonmembrane = binary_membranes.view('float32')
        vigra.filters.distanceTransform(
                binary_membranes,
                background=False,
                out=distance_to_nonmembrane,
                pixel_pitch = [anisotropy, 1., 1.])

        # Combine the inner/outer distance transforms
        distance_to_nonmembrane[distance_to_nonmembrane>0] -= 1
        distance_to_membrane[:] -= distance_to_nonmembrane

    return distance_to_membrane


def anisotropic_seeds(
        distance_to_membrane,
        anisotropy,
        sigma_seeds,
        group_seeds
        ):

    seeds = np.zeros_like(distance_to_membrane, dtype = 'uint32')
    seed_map = vigra.filters.gaussianSmoothing(distance_to_membrane, (1. / anisotropy, 1., 1.) )

    for z in xrange(distance_to_membrane.shape[0]):
        seeds_z  = vigra.analysis.localMaxima(seed_map[z], allowPlateaus=True, allowAtBorder=True, marker=np.nan)

        if group_seeds:
            seeds_z = group_seeds_by_distance( seeds_z, distance_to_membrane[z])
        else:
            seeds_z = vigra.analysis.labelMultiArrayWithBackground(seeds_z)

        seeds[z] = seeds_z

    return seeds


def ws_anisotropic_distance_transform(
        pmap,
        threshold,
        anisotropy,
        sigma_seeds,
        sigma_weights           = 0.,
        min_segment_size        = 0,
        preserve_membrane_pmaps = True,
        grow_on_pmap            = True,
        group_seeds             = False
        ):
    """
    Watershed on anisotropic distance transform on 3d probabiity map.

    @params:
    pmap: probability map, 3d numpy.ndarray of type float32.
    threshold: threshold for pixels that are considered in distance transform.
    anisotropy: anisotropy factor along the z axis.
    sigma_seeds: smoothing factor for distance transform used for finding seeds.
    sigma_weights: smoothing factor for heiht map used for the watershed (default 0.).
    min_segment_size: size filter for resulting segments (default 0 -> no size filtering).
    preserve_membrane: preserve membrane seeds (default: False).
    grow_on_pmap: grow on the probability map instead of distance transform (default: True).
    group_seeds: use heuristics to group adjacent seeds (default: False).
    @returns:
    fragments: numpy.ndarray of type uint32
    n_labels:  number of labels
    """

    # make sure we are in 3d and that first axis is z
    assert pmap.ndim == 3
    shape = pmap.shape
    assert shape[0] < shape[1] and shape[0] < shape[2]

    distance_to_membrane = signed_anisotropic_dt(pmap, threshold, anisotropy, preserve_membrane_pmaps)
    seeds = anisotropic_seeds(distance_to_membrane, anisotropy, sigma_seeds, group_seeds)


    if grow_on_pmap:
        hmap = pmap
    else:
        hmap = distance_to_membrane
        # Invert the DT: Watershed code requires seeds to be at minimums, not maximums
        hmap[:] *= -1

    if sigma_weights != 0.:
        hmap = vigra.filters.gaussianSmoothing(hmap, ( 1. / sigma_weights ) )

    offset = 0
    for z in xrange(shape[0]):
        max_z = iterative_inplace_watershed(hmap[z], seeds[z], min_segment_size, None)
        seeds[z] -= 1
        seeds[z] += offset
        # TODO make sure that this does not cause a label overlap by one between adjacent slices
        offset += max_z

    return seeds, offset
