import numpy as np
import datetime as DT
from . import sblib as sb
import os, glob
import pickle as pickle

def extract_time(data,index):
    """This function takes a dictionary [data] and pulles out all of the keys at specific index [index]
        specific to cBathy dictionary keys

    Args:
      data: dictionary
      index: index to be removed

    Returns:
      new dictionary with only the indexs selected returned

    """
    vars = list(data.keys())
    new = {}
    for vv in vars:
        if vv is 'xm' or vv is 'ym':
            new[vv] = data[vv]
        else:
            new[vv] = data[vv][index]
    return new

def cbathy_kalman_filter(new, prior, waveHs):
    """This function does a kalman filter designed for implmeneting wave height thresholds into the cbathy
    algorithm, this operates on a single time step only!!!

    Args:
      new(dict): a dictionary with keys associated with get data
         'xm': frf x coords

         'ym': frf y coords

         'time': current time

         'depthfCError': curent estimate error

         'depthfC': current estimate

      prior (dict): a saved dictionary with bathys derived from times when wave heights were below the threshold of choice
         'time':

         'depthKF': previous filtered estimate

         'P':
      waveHs (float): single wave height value


    Returns:
      new dictionary
         'P':

    """
    if type(prior['time']) == list and len(prior['time']) == 1:
        prior['time'] = prior['time'][0]

    n = 2.0
    Cq = 0.067
    sigmax = 100.
    x0 = 150.

    xlen = len(new['xm'])
    ylen = len(new['ym'])
    temp = new['time'] - prior['time']
    delt = temp.days + temp.seconds/(24.*3600.)
    ## maybe we flatten the arrays so we don't have to loop
    # need to make a new x array
    xarray = np.tile(new['xm'],(1,len(new['ym']))).T
   # for ix in range(len(new['xm'])):
    Q = Cq*waveHs**n*np.exp(-((xarray - x0)/sigmax)**2)

   #     for iy in range(len(new['ym'])):
    Pkm = prior['P'].flatten() + Q[:,0]*delt

    K = Pkm/(Pkm + new['depthfCError'].flatten()**2)
    
    hk = prior['depthKF'].flatten() + K*(new['depthfC'].flatten() - prior['depthKF'].flatten())

    Pk = (1-K)*Pkm

    #hnew = np.empty((hk.shape))
    #hnew[:] = np.NAN
    #pnew = np.empty((hk.shape))
    #pnew[:] = np.NAN
    
    #iin = (np.isnan(new['depthfC'].flatten())) #or (np.isnan(new['depthfCError'].flatten()))
    #hk[iin] = prior['depthKF'].flatten()[iin]
    #Pk[iin] = Pkm[iin]

    #iip = np.isnan(prior['depthKF'].flatten())
    #hk[iin] = new['depthfC'].flatten()[iip]
    #Pk[iin] = new['depthfCError'].flatten()[iip]**2.
    
# tests show below is the same
    # new['depthKF'][:] = 0.0
    # new['depthKFError'][:] = 0.0
    # new['P'][:] = 0.0
#    new['Q'][:] = 0.0
#     new['depthKF'] = hk.reshape((ylen,xlen))
# #    new['depthKFError'] = np.sqrt(Pk.reshape((ylen,xlen)))
#     new['P'] = Pk.reshape((ylen,xlen))
# #    new['Q'] = Q.reshape((ylen,xlen))
#     ## fill the new file with the old values when they have no values
#     idd = np.ma.getmask(new['depthKF'])
#     new['depthKF'][idd] = prior['depthKF'][idd]
#     new['P'][idd] = prior['P'][idd]
#     new['depthKFError'] = np.sqrt(new['P'])
    if isinstance(hk, np.ma.masked_array):
        idx = np.argwhere(hk.mask).squeeze()       # find idx of missing points in new array
    else:
        idx = np.argwhere(np.isnan(hk)).squeeze()
    hk[idx] = prior['depthKF'].flatten()[idx]  # fill kalman filtered depth estimates with old values when missing
    Pk[idx] = prior['P'].flatten()[idx]        # fill error variance with old values when missing
    # package for departure
    new['depthKF'] = hk.reshape((ylen,xlen))
    new['P'] = Pk.reshape((ylen,xlen))
    new['depthKFError'] = np.sqrt(new['P'])

    return new

def replacecBathyMasksWithNans(dictionary):
    """function will replace dictionary keys that are masked arrays filled with numpy.nans
    :param dictionary: an arbitrary dictionary with keys

    :return: unmasked dictonary with nans in place of mask=True
    """
    for var in dictionary:
        if isinstance(dictionary[var], np.ma.masked_array):
            dictionary[var] = np.ma.filled(dictionary[var], fill_value=np.nan)
    return dictionary

def cBathy_ThresholdedLogic(cBathy, rawspec, waveHsThreshold=1.2):
    """Logic associated with creating the wave height thresholded kalman filtered cBathy representation

    Args:
      cBathy: dictionary from go.getcBathy data
      rawspec: dictionary from go.getwavespec function
      waveHsThreshold: a decimal value for which to compare when generating the new kalman filter (Default value = 1.2)

    Returns:
      the original cBathy dictionary
           'ym': yfrf coords

           'yFRF': yfrf coords

           'epochtime': epoch time

           'xm': xfrf coords

           'xFRF': xfrf coords

           'depthKF': kalman filtered depth estimate (updated with only estimates below wave height threshold

           'depthfC': individual depth estimates

           'P': Process error

           'depthfCError: individual depth estimate error

           'surveyMeanTime': last time data was updated

           'elevation': negative depth KF values

           'time': date time objects for each filtered estimate

    """
    ##### define inital global variables for function
    version_prefix = 'cBKF-T' # assume only one version
    #### Find which pickle to load
    best = DT.timedelta(3002)  # needs to be within X days to start to be considered
    pickList = glob.glob('/home/number/cmtb/cBathy_Study/pickles/{}_*_TimeAvgcBathy*.pickle'.format(version_prefix))
    loadPickleFname = None
    # Sort through pickles containing good cBathy bathymetries
    for file in pickList:
        delta =  cBathy['time'][0] - DT.datetime.strptime(file.split('/')[-1].split('_')[1], '%Y%m%dT%H%M%SZ')  # days old
        if delta.total_seconds() > 0 and delta.total_seconds() < best.total_seconds() :
            best = delta  # the new delta is currently the best, save it as the best
            # change the current load name to the current best
            loadPickleFname = file #'cBathy_Study/pickles/%s_%s_%s_TimeAvgcBathy.pickle' %(version_prefix, timerun, file.split('/')[-1].split('_')[2])

    ##### begin Running logic
    # first ensure that the wave data and cbathy have same time step,
    # if they don't interpolate the wavdata to the cbathy time stamp
    if ~np.in1d(rawspec['time'], cBathy['time']).all():
        # interpolate the rawspec to the cbathy time frame
        rawspec['Hs'] = np.interp(cBathy['epochtime'], xp=rawspec['epochtime'], fp=rawspec['Hs'])
        rawspec['epochtime'] = cBathy['epochtime']
    try:
        time, idxObs, idxcBathy = sb.timeMatch(rawspec['epochtime'][:], list(range(rawspec['epochtime'][:].shape[0])),
                                               cBathy['epochtime'], list(range(len(cBathy['time']))))
        # find idx of waves below this value
        badIdx = np.argwhere(rawspec['Hs'][idxObs.astype(int)] > waveHsThreshold).squeeze()
    except TypeError:  # when cbath== None
        badIdx = np.array([])
    if isinstance(cBathy['depthKF'], np.ma.masked_array):
        cBathy = replacecBathyMasksWithNans(cBathy)

    ##########################################
    # Begin Thresholded kalman filtered logic
    #########################################
    ttO = np.size(cBathy['time'])-np.size(badIdx) # expected output time dimension
    depthKF = np.zeros((ttO, cBathy['depthKF'].shape[1], cBathy['depthKF'].shape[2]))
    depthKFE, P, depthfC, depthfCE = np.zeros_like(depthKF), np.zeros_like(depthKF), np.zeros_like(depthKF), np.zeros_like(depthKF)
    timeO, etimeO, rc = np.zeros((ttO), dtype=object), np.zeros((ttO)), 0
    if cBathy == None and loadPickleFname != None and os.path.isfile(loadPickleFname):
        # need to catch the Nones before trying to loop over it
        # load Old Cbathy
        # print '          CBThresh: No cbathy found at this Time (dark?), using old Good Cbathy .... loading Pickle: %s' % loadPickleFname
        # with open(loadPickleFname, 'rb') as handle:
        #     cBathy = pickle.load(file=handle)
        pass # don't make if its not new cBathy estimate
    else:
        for tt in range(len(cBathy['time'])):  # this may need to be changed for not implmented error above
            # -- may need this for more time steps np.size(badIdx) < np.size(idxObs) and
            # figure out if we have good waves (createing good cbathy) then if so do the new kalman filter logic here
            if tt not in badIdx:  # if there's at least 1 good value,
                # cbathy at time tt is considered good!
                if rc >= 1:
                    cbathyold = {'ym': cBathy['ym'],
                                 'epochtime': etimeO[rc-1],
                                 'xm': cBathy['xm'],
                                 'depthKF': depthKF[rc-1],
                                 'depthfC': depthfC[rc-1],
                                 'P': P[rc-1],
                                 'depthfCError': depthfCE[rc-1],
                                 # 'k',
                                 # 'depth':,
                                 # 'fB': ,
                                 'time': timeO[rc-1],
                                 'depthKFError': depthKFE[rc-1]}
                elif loadPickleFname is not None and os.path.isfile(loadPickleFname):
                    with open(loadPickleFname, 'rb') as handle:
                        cbathyold = pickle.load(handle)
                        print('     CBThresh: wave height good, Kalman filtering from %s' % loadPickleFname)
                    if cbathyold['elevation'].shape != cBathy['depthKF'].shape[1:] :# load from background
                        print('  Loading from background, you changed your grid shape')
                        from getdatatestbed import getDataFRF
                        go = getDataFRF.getObs(cBathy['time'][0], cBathy['time'][-1])
                        full = go.getBathyGridcBathy()
                        cbathyold = sb.reduceDict(full,-1)
                        xinds = np.where(np.in1d(cbathyold['xm'], cBathy['xm']))[0]
                        yinds = np.where(np.in1d(cbathyold['ym'], cBathy['ym']))[0]
                        for key in list(cbathyold.keys()):
                            if key is 'xm':
                                cbathyold[key] = cbathyold[key][xinds]
                            elif key is 'ym':
                                cbathyold[key] = cbathyold[key][xinds]
                            elif key not in ['epochtime', 'time', 'xm', 'ym']:
                                cbathyold[key] = cbathyold[key][slice(yinds[0], yinds[-1]+1), slice(xinds[0], xinds[-1]+1)]
                else:
                    raise ImportError('You need a cBathy to seed the first kalman filter step ')

                cBathySingle = extract_time(cBathy, tt)
                temp = cbathy_kalman_filter(cBathySingle, cbathyold, rawspec['Hs'])
                # overwrite old kalman filtered results with new kalman filtered results
                depthKF[rc] = np.ma.filled(temp['depthKF'], fill_value=np.nan) # temp['depthKF']
                depthKFE[rc] = np.ma.filled(temp['depthKFError'], fill_value=np.nan)
                P[rc] = np.ma.filled(temp['P'], fill_value=np.nan)
                depthfCE[rc] = np.ma.filled(temp['depthfCError'], fill_value=np.nan)
                depthfC[rc] = np.ma.filled(temp['depthfC'], fill_value=np.nan)
                timeO[rc] = temp['time']
                etimeO[rc] = temp['epochtime']
                rc +=1

            else:  # cbathy @ time tt is considered bad!
                pass
        if np.size(timeO)>0:
            # Done creating the 'day's newcBathy output
            # save last file
            savePickleFname = '/home/number/cmtb/cBathy_Study/pickles/%s_%s_TimeAvgcBathy.pickle' % (
                version_prefix, timeO[-1].strftime('%Y%m%dT%H%M%SZ'))
            print('      CBThresh: Kalman filtered, now saving pickle {}'.format(savePickleFname))
            cBathyOut = {'ym': cBathy['ym'],
                         'yFRF': cBathy['ym'],
                         'epochtime': etimeO,
                         'xm': cBathy['xm'],
                         'xFRF': cBathy['xm'],
                         'depthKF': depthKF,
                         'depthfC': depthfC,
                         'P': P,
                         'depthfCError': depthfCE,
                         'surveyMeanTime': etimeO[-1],
                         'elevation': -depthKF,
                         # 'k',
                         # 'depth':,
                         # 'fB': ,
                         'time': timeO,
                         'depthKFError': depthKFE}

            with open(savePickleFname, 'wb') as handle:
                # reduce if its more than one (still works on single dictionary)
                cBathyOutPick = sb.reduceDict(cBathyOut, -1)
                pickle.dump(cBathyOutPick, file=handle, protocol=pickle.HIGHEST_PROTOCOL)
        else:
            cBathyOut = None
    return cBathyOut