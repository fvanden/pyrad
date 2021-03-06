"""
pyrad.util.radar_utils
======================

Miscellaneous functions dealing with radar data

.. autosummary::
    :toctree: generated/

    time_series_statistics
    join_time_series
    get_range_bins_to_avg
    find_ray_index
    find_rng_index
    time_avg_range
    get_closest_solar_flux
    create_sun_hits_field
    create_sun_retrieval_field
    compute_quantiles
    compute_quantiles_from_hist
    compute_quantiles_sweep
    compute_histogram
    compute_histogram_sweep
    compute_2d_stats
    compute_2d_hist
    quantize_field

"""
from warnings import warn
from copy import deepcopy
import datetime

import numpy as np
import pandas as pd
import scipy

import pyart


def time_series_statistics(t_in_vec, val_in_vec, avg_time=3600,
                           base_time=1800, method='mean', dropnan=False):
    """
    Computes statistics over a time-averaged series

    Parameters
    ----------
    t_in_vec : datetime array
        the input date and time array
    val_in_vec : float array
        the input values array
    avg_time : int
        averaging time [s]
    base_time : int
        base time [s]
    method : str
        statistical method
    dropnan : boolean
        if True remove NaN from the time series

    Returns
    -------
    t_out_vec : datetime array
        the output date and time array
    val_out_vec : float array
        the output values array

    """
    df_in = pd.DataFrame(data=val_in_vec, index=pd.DatetimeIndex(t_in_vec))
    df_out = getattr(df_in.resample(str(avg_time)+'S', closed='right',
                     label='right', base=base_time), method)()
    if dropnan is True:
        df_out = df_out.dropna(how='any')
    t_out_vec = df_out.index.to_pydatetime()
    val_out_vec = df_out.values.flatten()

    return t_out_vec, val_out_vec


def join_time_series(t1, val1, t2, val2, dropnan=False):
    """
    joins time_series

    Parameters
    ----------
    t1 : datetime array
        time of first series
    val1 : float array
        value of first series
    t2 : datetime array
        time of second series
    val2 : float array
        value of second series
    dropnan : boolean
        if True remove NaN from the time series

    Returns
    -------
    t_out_vec : datetime array
        the resultant date time after joining the series
    val1_out_vec : float array
        value of first series
    val2_out_vec : float array
        value of second series

    """
    df1 = pd.DataFrame(data=val1, index=pd.DatetimeIndex(t1))
    df2 = pd.DataFrame(data=val2, index=pd.DatetimeIndex(t2))
    df_out = pd.concat([df1, df2], join='outer', axis=1)
    if dropnan is True:
        df_out = df_out.dropna(how='any')
    t_out_vec = df_out.index.to_pydatetime()
    val1_out_vec = df_out.values[:, 0].flatten()
    val2_out_vec = df_out.values[:, 1].flatten()

    return t_out_vec, val1_out_vec, val2_out_vec


def get_range_bins_to_avg(rad1_rng, rad2_rng):
    """
    Compares the resolution of two radars and determines if and which radar
    has to be averaged and the length of the averaging window

    Parameters
    ----------
    rad1_rng : array
        the range of radar 1
    rad2_rng : datetime
        the range of radar 2

    Returns
    -------
    avg_rad1, avg_rad2 : Boolean
        Booleans specifying if the radar data has to be average in range
    avg_rad_lim : array with two elements
        the limits to the average (centered on each range gate)

    """
    rad1_res = rad1_rng[1]-rad1_rng[0]
    rad2_res = rad2_rng[1]-rad2_rng[0]
    res_ratio = rad1_res/rad2_res

    avg_rad1 = False
    avg_rad2 = False
    avg_rad_lim = None
    if res_ratio > 1.5:
        avg_rad2 = True
        nbins = int(res_ratio)
        if nbins % 2 == 0:
            avg_rad_lim = [-int(nbins/2)-1, int(nbins/2)]
        else:
            avg_rad_lim = [-int((nbins-1)/2), int((nbins-1)/2)]
    elif res_ratio < 1./1.5:
        avg_rad1 = True
        nbins = int(1./res_ratio)
        if nbins % 2 == 0:
            avg_rad_lim = [-int(nbins/2)-1, int(nbins/2)]
        else:
            avg_rad_lim = [-int((nbins-1)/2), int((nbins-1)/2)]

    return avg_rad1, avg_rad2, avg_rad_lim


def find_ray_index(ele_vec, azi_vec, ele, azi, ele_tol=0., azi_tol=0.,
                   nearest='azi'):
    """
    Find the ray index corresponding to a particular elevation and azimuth

    Parameters
    ----------
    ele_vec, azi_vec : float arrays
        The elevation and azimuth data arrays where to look for
    ele, azi : floats
        The elevation and azimuth to search
    ele_tol, azi_tol : floats
        Tolerances [deg]
    nearest : str
        criteria to define wich ray to keep if multiple rays are within
        tolerance. azi: nearest azimuth, ele: nearest elevation

    Returns
    -------
    ind_ray : int
        The ray index

    """
    ind_ray = np.where(np.logical_and(
        np.logical_and(ele_vec <= ele+ele_tol, ele_vec >= ele-ele_tol),
        np.logical_and(azi_vec <= azi+azi_tol, azi_vec >= azi-azi_tol)))

    if len(ind_ray[0]) == 0:
        return None
    if len(ind_ray[0]) == 1:
        return ind_ray[0]

    if nearest == 'azi':
        ind_min = np.argmin(np.abs(azi_vec[ind_ray]-azi))
    else:
        ind_min = np.argmin(np.abs(ele_vec[ind_ray]-ele))

    return ind_ray[ind_min]


def find_rng_index(rng_vec, rng, rng_tol=0.):
    """
    Find the range index corresponding to a particular range

    Parameters
    ----------
    rng_vec : float array
        The range data array where to look for
    rng : float
        The range to search
    rng_tol : float
        Tolerance [m]

    Returns
    -------
    ind_rng : int
        The range index

    """
    dist = np.abs(rng_vec-rng)
    ind_rng = np.argmin(dist)
    if dist[ind_rng] > rng_tol:
        return None

    return ind_rng


def time_avg_range(timeinfo, avg_starttime, avg_endtime, period):
    """
    finds the new start and end time of an averaging

    Parameters
    ----------
    timeinfo : datetime
        the current volume time
    avg_starttime : datetime
        the current average start time
    avg_endtime: datetime
        the current average end time
    period: float
        the averaging period

    Returns
    -------
    new_starttime : datetime
        the new average start time
    new_endtime : datetime
        the new average end time

    """
    new_starttime = deepcopy(avg_starttime)
    new_endtime = deepcopy(avg_endtime)

    within_range = False
    while not within_range:
        if timeinfo > new_endtime:
            new_starttime += datetime.timedelta(seconds=period)
            new_endtime += datetime.timedelta(seconds=period)
        else:
            within_range = True

    return new_starttime, new_endtime


def get_closest_solar_flux(hit_datetime_list, flux_datetime_list,
                           flux_value_list):
    """
    finds the solar flux measurement closest to the sun hit

    Parameters
    ----------
    hit_datetime_list : datetime array
        the date and time of the sun hit
    flux_datetime_list : datetime array
        the date and time of the solar flux measurement
    flux_value_list: ndarray 1D
        the solar flux values

    Returns
    -------
    flux_datetime_closest_list : datetime array
        the date and time of the solar flux measurement closest to sun hit
    flux_value_closest_list : ndarray 1D
        the solar flux values closest to the sun hit time

    """
    flux_datetime_closest_list = list()
    flux_value_closest_list = np.ma.empty(len(hit_datetime_list))
    flux_value_closest_list[:] = np.ma.masked

    i = 0
    for datetime in hit_datetime_list:
        flux_datetime_closest = min(
            flux_datetime_list, key=lambda x: abs(x-datetime))
        flux_datetime_closest_list.append(flux_datetime_closest)

        # solar flux observation within 24h of sun hit
        time_diff = abs(flux_datetime_closest-datetime).total_seconds()
        if time_diff < 86400.:
            ind = flux_datetime_list.index(flux_datetime_closest)
            flux_value_closest_list[i] = flux_value_list[ind]
        else:
            warn('Nearest solar flux observation further than ' +
                 str(time_diff)+' s in time')
        i += 1

    return flux_datetime_closest_list, flux_value_closest_list


def create_sun_hits_field(rad_el, rad_az, sun_el, sun_az, data, imgcfg):
    """
    creates a sun hits field from the position and power of the sun hits

    Parameters
    ----------
    rad_el, rad_az, sun_el, sun_az : ndarray 1D
        azimuth and elevation of the radar and the sun respectively in degree
    data : masked ndarray 1D
        the sun hit data
    imgcfg: dict
        a dictionary specifying the ranges and resolution of the field to
        create

    Returns
    -------
    field : masked ndarray 2D
        the sun hit field

    """
    if len(data.compressed()) == 0:
        warn('No valid sun hits to plot.')
        return None

    azmin = imgcfg['azmin']
    azmax = imgcfg['azmax']
    elmin = imgcfg['elmin']
    elmax = imgcfg['elmax']
    azres = imgcfg['azres']
    elres = imgcfg['elres']

    mask = np.ma.getmaskarray(data)
    rad_el = rad_el[~mask]
    rad_az = rad_az[~mask]
    sun_el = sun_el[~mask]
    sun_az = sun_az[~mask]
    data = data[~mask]

    d_el = rad_el-sun_el
    d_az = (rad_az-sun_az)*np.cos(sun_el*np.pi/180.)

    npix_az = int((azmax-azmin)/azres)
    npix_el = int((elmax-elmin)/elres)
    field = np.ma.zeros((npix_az, npix_el))
    field[:] = np.ma.masked

    ind_az = ((d_az+azmin)/azres).astype(int)
    ind_el = ((d_el+elmin)/elres).astype(int)

    field[ind_az, ind_el] = data

    return field


def create_sun_retrieval_field(par, imgcfg):
    """
    creates a sun retrieval field from the retrieval parameters

    Parameters
    ----------
    par : ndarray 1D
        the 5 retrieval parameters
    imgcfg: dict
        a dictionary specifying the ranges and resolution of the field to
        create

    Returns
    -------
    field : masked ndarray 2D
        the sun retrieval field

    """
    azmin = imgcfg['azmin']
    azmax = imgcfg['azmax']
    elmin = imgcfg['elmin']
    elmax = imgcfg['elmax']
    azres = imgcfg['azres']
    elres = imgcfg['elres']

    npix_az = int((azmax-azmin)/azres)
    npix_el = int((elmax-elmin)/elres)

    field = np.ma.zeros((npix_az, npix_el))
    field[:] = np.ma.masked

    d_az = np.array(np.array(range(npix_az))*azres+azmin)
    d_el = np.array(np.array(range(npix_el))*elres+elmin)

    d_az_mat = np.broadcast_to(d_az.reshape(npix_az, 1), (npix_az, npix_el))
    d_el_mat = np.broadcast_to(d_el.reshape(1, npix_el), (npix_az, npix_el))

    field = (par[0]+par[1]*d_az_mat+par[2]*d_el_mat+par[3]*d_az_mat*d_az_mat +
             par[4]*d_el_mat*d_el_mat)

    return field


def compute_quantiles(field, quantiles=None):
    """
    computes quantiles

    Parameters
    ----------
    field : ndarray 2D
        the radar field
    ray_start, ray_end : int
        starting and ending ray indexes
    quantiles: float array
        list of quantiles to compute

    Returns
    -------
    quantiles : float array
        list of quantiles
    values : float array
        values at each quantile

    """
    if quantiles is None:
        quantiles = [10., 20., 30., 40., 50., 60., 70., 80., 90.]
        warn('No quantiles have been defined. Default ' + str(quantiles) +
             ' will be used')
    nquantiles = len(quantiles)
    values = np.ma.zeros(nquantiles)
    values[:] = np.ma.masked

    data_valid = field.compressed()
    if np.size(data_valid) < 10:
        warn('Unable to compute quantiles. Not enough valid data')
        return quantiles, values

    for i in range(nquantiles):
        values[i] = np.percentile(data_valid, quantiles[i])

    return quantiles, values


def compute_quantiles_from_hist(bins, hist, quantiles=None):
    """
    computes quantiles from histograms

    Parameters
    ----------
    bins : ndarray 1D
        the bins
    hist : ndarray 1D
        the histogram
    quantiles: float array
        list of quantiles to compute

    Returns
    -------
    quantiles : float array
        list of quantiles
    values : float array
        values at each quantile

    """
    if quantiles is None:
        quantiles = [10., 20., 30., 40., 50., 60., 70., 80., 90.]
        warn('No quantiles have been defined. Default ' + str(quantiles) +
             ' will be used')
    nquantiles = len(quantiles)
    values = np.ma.empty(nquantiles)
    values[:] = np.ma.masked

    # check if all elements in histogram are masked values
    mask = np.ma.getmaskarray(hist)
    if mask.all():
        return quantiles, values

    np_t = np.ma.sum(hist)
    if np_t < 10:
        return quantiles, values

    freq = hist/np_t
    rel_freq = np.ma.cumsum(freq)

    percentiles = quantiles/100.
    for i in range(nquantiles):
        values[i] = bins[rel_freq >= percentiles[i]][0]

    return quantiles, values


def compute_quantiles_sweep(field, ray_start, ray_end, quantiles=None):
    """
    computes quantiles of a particular sweep

    Parameters
    ----------
    field : ndarray 2D
        the radar field
    ray_start, ray_end : int
        starting and ending ray indexes
    quantiles: float array
        list of quantiles to compute

    Returns
    -------
    quantiles : float array
        list of quantiles
    values : float array
        values at each quantile

    """
    if quantiles is None:
        quantiles = [10., 20., 30., 40., 50., 60., 70., 80., 90.]
        warn('No quantiles have been defined. Default ' + str(quantiles) +
             ' will be used')
    nquantiles = len(quantiles)
    values = np.ma.zeros(nquantiles)
    values[:] = np.ma.masked

    data_valid = field[ray_start:ray_end+1, :].compressed()
    if np.size(data_valid) < 10:
        warn('Unable to compute quantiles. Not enough valid data')
        return quantiles, values

    for i in range(nquantiles):
        values[i] = np.percentile(data_valid, quantiles[i])

    return quantiles, values


def compute_histogram(field, field_name, step=None):
    """
    computes histogram of the data

    Parameters
    ----------
    field : ndarray 2D
        the radar field
    field_name: str
        name of the field
    step : float
        size of bin

    Returns
    -------
    bins : float array
        interval of each bin
    values : float array
        values at each bin

    """
    bins = get_histogram_bins(field_name, step=step)
    field[field < bins[0]] = bins[0]
    field[field > bins[-1]] = bins[-1]
    values = field.compressed()

    return bins, values


def compute_2d_stats(field1, field2, field_name1, field_name2, step1=None,
                     step2=None):
    """
    computes histogram of the data

    Parameters
    ----------
    field : ndarray 2D
        the radar field
    field_name: str
        name of the field
    step : float
        size of bin

    Returns
    -------
    bins : float array
        interval of each bin
    values : float array
        values at each bin

    """
    if len(field1) == 0 or len(field2) == 0:
        warn('Unable to compute 2D histogram. Empty field')
        stats = {
            'npoints': 0,
            'meanbias': np.ma.asarray(np.ma.masked),
            'medianbias': np.ma.asarray(np.ma.masked),
            'modebias': np.ma.asarray(np.ma.masked),
            'corr': np.ma.asarray(np.ma.masked),
            'slope': np.ma.asarray(np.ma.masked),
            'intercep': np.ma.asarray(np.ma.masked),
            'intercep_slope_1': np.ma.asarray(np.ma.masked)
        }
        return None, None, None, stats

    hist_2d, bins1, bins2 = compute_2d_hist(
        field1, field2, field_name1, field_name2, step1=step1, step2=step2)
    npoints = len(field1)
    meanbias = 10.*np.ma.log10(
        np.ma.mean(np.ma.power(10., 0.1*field2)) /
        np.ma.mean(np.ma.power(10., 0.1*field1)))
    medianbias = np.ma.median(field2-field1)
    ind_max_val1, ind_max_val2 = np.where(hist_2d == np.ma.amax(hist_2d))
    modebias = bins2[ind_max_val2[0]]-bins1[ind_max_val1[0]]
    slope, intercep, corr, pval, stderr = scipy.stats.linregress(
        field1, y=field2)
    intercep_slope_1 = np.ma.mean(field2-field1)

    stats = {
        'npoints': npoints,
        'meanbias': np.ma.asarray(meanbias),
        'medianbias': np.ma.asarray(medianbias),
        'modebias': np.ma.asarray(modebias),
        'corr': np.ma.asarray(corr),
        'slope': np.ma.asarray(slope),
        'intercep': np.ma.asarray(intercep),
        'intercep_slope_1': np.ma.asarray(intercep_slope_1)
    }

    return hist_2d, bins1, bins2, stats


def compute_2d_hist(field1, field2, field_name1, field_name2, step1=None,
                    step2=None):
    """
    computes histogram of the data

    Parameters
    ----------
    field : ndarray 2D
        the radar field
    field_name: str
        name of the field
    step : float
        size of bin

    Returns
    -------
    bins : float array
        interval of each bin
    values : float array
        values at each bin

    """
    bins1 = get_histogram_bins(field_name1, step=step1)
    bins2 = get_histogram_bins(field_name2, step=step2)

    field1[field1 < bins1[0]] = bins1[0]
    field1[field1 > bins1[-1]] = bins1[-1]

    field2[field2 < bins2[0]] = bins2[0]
    field2[field2 > bins2[-1]] = bins2[-1]

    fill_value = pyart.config.get_fillvalue()
    return np.histogram2d(
        field1.filled(fill_value=fill_value),
        field2.filled(fill_value=fill_value), bins=[bins1, bins2])


def quantize_field(field, field_name, step):
    """
    quantizes data

    Parameters
    ----------
    field : ndarray 2D
        the radar field
    field_name: str
        name of the field
    step : float
        size of bin

    Returns
    -------
    fieldq : ndarray 2D
        The quantized field
    values : float array
        values at each bin

    """
    vmin, vmax = pyart.config.get_field_limits(field_name)
    field[field < vmin] = vmin
    field[field > vmax] = vmax
    fieldq = ((field+vmin)/step+1).astype(int)

    return fieldq.filled(fill_value=0)


def compute_histogram_sweep(field, ray_start, ray_end, field_name, step=None):
    """
    computes histogram of the data in a particular sweep

    Parameters
    ----------
    field : ndarray 2D
        the radar field
    ray_start, ray_end : int
        starting and ending ray indexes
    field_name: str
        name of the field
    step : float
        size of bin

    Returns
    -------
    bins : float array
        interval of each bin
    values : float array
        values at each bin

    """
    bins = get_histogram_bins(field_name, step=step)
    field_sweep = field[ray_start:ray_end+1, :]
    field_sweep[field_sweep < bins[0]] = bins[0]
    field_sweep[field_sweep > bins[-1]] = bins[-1]
    values = field_sweep[ray_start:ray_end+1, :].compressed()

    return bins, values


def get_histogram_bins(field_name, step=None):
    """
    gets the histogram bins using the range limits of the field as defined
    in the Py-ART config file.

    Parameters
    ----------
    field_name: str
        name of the field
    step : float
        size of bin

    Returns
    -------
    bins : float array
        interval of each bin

    """
    vmin, vmax = pyart.config.get_field_limits(field_name)
    if step is None:
        step = (vmax-vmin)/50.
        warn('No step has been defined. Default '+str(step)+' will be used')

    return np.linspace(vmin, vmax, num=int((vmax-vmin)/step))
