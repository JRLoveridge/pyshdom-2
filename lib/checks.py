"""
This module contains functions to perform common checks on
xarray.Dataset or xarray.DataArray inputs to methods in pyshdom.

Many objects and functions in pyshdom expect variables to have certain
names or certain dimension names and for their values to conform to
certain rules; positivity, within a certain range etc. As users may also
want to create their own workflow rather than relying on some of the methods
in pyshdom these checks are provided to help catch unexpected inputs.
"""
import typing

import numpy as np

import pyshdom.exceptions

def check_exists(dataset, *names):
    """Checks if certain Variables are present in a dataset.

    Parameters
    ----------
    dataset : xr.Dataset
        The xr.Dataset to check if variables are present.
    names : string
        The names of Variables expected to be contained in `dataset`.

    Raises
    ------
    KeyError
        If `dataset` is not hashable by any of `names`.
    """
    for name in names:
        try:
            dataset[name]
        except KeyError as err:
            raise type(err)(str("Expected variable with name '{}' in dataset".format(name)))

def check_positivity(dataset, *names, precision=7):
    """
    Checks if certain variables are positive (>=0.0) up to a specified precision.

    Checks whether each variable is >=0.0. If any value in a variable contains
    values <= 0.0 then that variable is rounded to the number of decimal places
    specified by `precision`. If negative values are still present, then an
    Exception is raised.

    Parameters
    ----------
    dataset : xr.Dataset
        The xr.Dataset to check if variables are positive (>=0.0)
    names : string
        The names of Variables to be checked in `dataset`.
    precision : int
        The number of decimal places up to which each variable should be
        distinguishable from zero.

    Raises
    ------
    KeyError
        If the variable is not found within the `dataset`.
    NegativeValueError
        If any of `names` in `dataset` contain negative values.
        See pyshdom.exceptions.NegativeValueError

    Notes
    -----
    This does modify `dataset` inplace. The rounding was implemented to deal with
    xarray's interpolation routine creating very small (1e-18) negative values
    instead of zeros when interpolating a dataset onto its own coordinates due to
    rounding errors. The default choice of `precision` is set to 7 due to the
    use of single precision in the SHDOM routines.
    """
    check_exists(dataset, *names)
    for name in names:
        variable = dataset[name]
        if not np.all(variable.data >= 0.0):
            dataset[name][:] = np.round(variable, decimals=precision)
            if not np.all(variable.data >= 0.0):
                raise pyshdom.exceptions.NegativeValueError(
                    "Negative values found in '{}'".format(name)
                    )

def check_range(dataset, **checkkwargs):
    """
    Checks if variables within a dataset have values within a specified range.

    Parameters
    ----------
    dataset : xr.Dataset
        The xr.Dataset to check.
    checkkwargs : dict
        Each kwarg/key should be the name of the variable to check. The value
        should be a Tuple/List of floats which are the (min, max) of the
        range that the variable should be contained in (inclusive).

    Raises
    ------
    KeyError
        If the variable is not found within the `dataset`.
    pyshdom.exceptions.OutOfRangeError
        If any value is out of range.
    """
    check_exists(dataset, *checkkwargs)
    for name, (low, high) in checkkwargs.items():
        data = dataset[name]
        if not np.all((low <= data) & (data <= high)):
            raise pyshdom.exceptions.OutOfRangeError(
                "Values outside of range '[{}, {}]' found in variable '{}'".format(
                    low, high, name)
            )

def check_hasdim(dataset, **checkkwargs):
    """Checks if variables have specified dimensions.

    Parameters
    ----------
    dataset : xr.Dataset
        The xr.Dataset to check.
    checkkwargs : dict
        Each kwarg/key should be the name of the variable to check. The value
        should be a Tuple/List of strings which are the names of the dimensions
        that each variable is expected to have.

    Raises
    ------
    KeyError
        If the variable is not found within the `dataset`.
    pyshdom.exceptions.MissingDimensionError
        If any variable in `dataset` does not have any of the specified
        dimension names.
    """
    check_exists(dataset, *checkkwargs)
    for name, dim_names in checkkwargs.items():
        if not isinstance(dim_names, (typing.Dict, typing.List, typing.Tuple)):
            dim_names = [dim_names]
        for dim_name in dim_names:
            if dim_name not in dataset[name].dims:
                raise pyshdom.exceptions.MissingDimensionError(
                    "Expected '{}' to have dimension '{}'".format(
                        name, dim_name)
                    )

def check_grid(dataset):
    """
    Check if the dataset can act as a grid for SHDOM.

    Checks if the dataset has coordinates labeled 'x', 'y', 'z' and variables
    'delx' and 'dely'. The 'x' and 'y' should be equispaced and consistent
    with the 'delx' and 'dely', The 'z' should contain at least two points and
    be positive and strictly increasing.
    These are the requirements for SHDOM grid (and solver.RTE)

    Parameters
    ----------
    dataset : xr.Dataset/ xr.DataArray
        The dataset to check if the coordinates conform to the requirements.

    Raises
    ------
    KeyError
        If any of the required variables/coordinates don't exist.
    pyshdom.exceptions.GridError
        If the grid does not met any of the requirements.
    """
    pyshdom.checks.check_exists(dataset, 'x', 'y', 'z', 'delx', 'dely')
    for dimension, deldim in zip(('x', 'y'), ('delx', 'dely')):

        if dataset[dimension][0] != 0.0:
            raise pyshdom.exceptions.GridError(
                "Grid dimension '{}' should start from 0.0".format(dimension)
                )
        if dataset[dimension].size > 1:
            diffx = dataset[dimension].diff(dimension).data
            if not np.allclose(diffx, diffx[0], atol=1e-6):
                raise pyshdom.exceptions.GridError(
                    "Grid dimension '{}' is not equispaced.".format(dimension)
                    )
            if not np.allclose(diffx[0], dataset[deldim]):
                raise pyshdom.exceptions.GridError(
                    "'{a}' is not consistent with '{b}'. "
                    "'{a}' should be set based on '{b}', see grid.make_grid for details.".format(
                        a=deldim, b=dimension)
                    )
            if not np.all(diffx > 0.0):
                raise pyshdom.exceptions.GridError(
                    "Grid dimension '{}' is not strictly increasing.".format(dimension)
                    )
        if dataset[deldim] <= 0.0:
            raise pyshdom.exceptions.GridError(
                "Grid dimension '{}' is not strictly increasing.".format(dimension)
                )
    if not np.all(dataset.z >= 0.0) & np.all(dataset.z.diff('z') > 0.0) & (dataset.z.size >= 2):
        raise pyshdom.exceptions.GridError(
            "Grid dimension 'z' should be positive, strictly increasing and "
            "have 2 or more elements."
            )

def check_legendre(dataset):
    """
    Check if the dataset contains a correctly formatted Legendre/Phase function
    table for use in SHDOM.

    Parameters
    ----------
    dataset : xr.Dataset/ xr.DataArray
        The dataset to check if the coordinates conform to the requirements.

    Raises
    ------
    KeyError
        if 'legcoef' does not exist in the dataset.
    pyshdom.exceptions.MissingDimensionError
        If 'legcoef' does not have 'stokes_index' and 'legendre_index'
        dimensions.
    pyshdom.exceptions.LegendreTableError
        If any of the other requirements are not met.
    """
    check_hasdim(dataset, legcoef=['stokes_index', 'legendre_index'])
    if dataset['legcoef'].sizes['stokes_index'] != 6:
        raise pyshdom.exceptions.LegendreTableError(
            "'stokes_index' dimension of 'legcoef' must have 6 components."
            )
    legendre_table = dataset['legcoef']
    if not np.allclose(legendre_table[0, 0], 1.0, atol=1e-7):
        raise pyshdom.exceptions.LegendreTableError(
            "0th Legendre/Wigner Coefficients must be normalized to 1.0")
    if not np.all((legendre_table[0, 1]/3.0 >= -1.0) & (legendre_table[0, 1]/3.0 <= 1.0)):
        raise pyshdom.exceptions.LegendreTableError(
            "Asymmetry Parameter (1st Legendre coefficient divided by 3)"
            "is not in the range [-1.0, 1.0]")

def check_sensor(dataset):
    """
    Tests a dataset to make sure it has all of the requirements to be used as a sensor
    by SHDOM for producing synthetic measurements.

    This tests the ranges of the geometric variables for both pixel and ray variables
    and ensures that they have correctly named dimensions.

    Parameters
    ----------
    dataset : xr.Dataset
        The dataset to check to see if it can act as a sensor.

    Raises
        KeyError
            If any of the expected variables are not present.
        pyshdom.exceptions.MissingDimensionError
            If any of the expected variables do not have correctly named dimensions.
        pyshdom.exceptions.NegativeValueError
            If the vertical coordinate or wavelength is not positive
        ValueError
            If there are viewing zenith values of 90 degrees (horizontal) which is
            not allowed by SHDOM.
            If invalid values for the 'stokes_index' coordinate are provided or
            more than one boolean is provided for 'use_subpixel_rays'.
        pyshdom.exceptions.OutOfRangeError
            If the cosine of viewing zenith are not in the range [-1.0 , 1.0] or
            the viewing azimuth angles are not in the range [-pi, pi]
        TypeError
            If the 'stokes'/'use_subpixel_rays' variables are not of boolean type.
    """
    check_hasdim(dataset, ray_mu='nrays', ray_phi='nrays', ray_x='nrays',
                 ray_y='nrays', ray_z='nrays', cam_mu='npixels', cam_phi='npixels',
                 cam_x='npixels', cam_y='npixels', cam_z='npixels', pixel_index='nrays',
                 ray_weight='nrays')
    check_positivity(dataset, 'cam_z', 'ray_z')
    check_positivity(dataset, 'wavelength')
    check_range(dataset, cam_mu=(-1.0, 1.0), ray_mu=(-1.0, 1.0))
    #check_range(dataset, ray_phi=(-np.pi, np.pi), cam_phi=(-np.pi, np.pi))

    if (np.any(dataset.cam_mu) == 0.0) or np.any(dataset.ray_mu == 0.0):
        raise ValueError("Values of `mu` (cam_mu or ray_mu) cannot be 0.0")
    check_exists(dataset, 'stokes_index')
    for i in dataset.stokes_index:
        if i not in ('I', 'Q', 'U', 'V'):
            raise ValueError(
                "Invalid Stokes components '{}' found in sensor dataset."
                " Valid values are 'I', 'Q', 'U', 'V'.".format(i)
                )
    check_hasdim(dataset, stokes='stokes_index')
    if dataset.stokes.dtype != np.bool:
        raise TypeError("'stokes' variable in sensor dataset should be of boolean type.")
    if dataset.use_subpixel_rays.dtype != np.bool:
        raise TypeError("'use_subpixel_rays' variable in sensor dataset should be of boolean type.")
    if dataset.use_subpixel_rays.size != 1:
        raise ValueError("'use_subpixel_rays' variable should have a single value shape=(1,).")
