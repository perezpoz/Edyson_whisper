import time
import subprocess
import random
import sys
sys.path.append("../python")
from HTK import HTKFile
import numpy as np
import os
import wave
import contextlib
#from sklearn.manifold import TSNE
from sklearn.decomposition import PCA
from sklearn.manifold import Isomap
from MulticoreTSNE import MulticoreTSNE as TSNE
from pydub import AudioSegment
import csv
#from minisom import MiniSom
import sompy
import umap
from sklearn.cluster import KMeans
from sklearn.cluster import DBSCAN
#from autoencoder import AE
from scipy import signal
import scipy.io.wavfile as wavfile
from sklearn.decomposition import TruncatedSVD

###
import scipy.signal.windows as win
import scipy.stats as stats
from librosa.feature import delta
from rasta import rastaplp
###

smilextract = os.path.join(os.path.dirname(__file__), '..', 'opensmile', 'bin', 'SMILExtract')
config_dir = os.path.join(os.path.dirname(__file__), '..', 'opensmile', 'config', 'mfcc')
static_dir = os.path.join(os.path.dirname(__file__), '..', 'web', 'static')

color_dict = {
    "-1": "black",
    "0": "blue",
    "1": "green",
    "2": "yellow",
    "3": "red",
    "4": "purple",
    "5": "orange",
    "6": "teal",
    "7": "brown",
    "8": "black",
    "9": "blue",
    "10": "green",
    "11": "yellow",
    "12": "red",
    "13": "purple",
    "14": "orange",
    "15": "teal",
    "16": "brown",
    "17": "black",
    "18": "blue",
    "19": "green",
}

def update_config(config_file, segment_size, step_size):
    print(config_file)
    with open(config_file, "r", encoding='windows-1252') as f:
        lines = f.readlines()
    with open(config_file, "w", encoding='windows-1252') as f:
        for line in lines:
            frameSize = 0.025
            frameStep = 0.01
            if line.startswith('frameSize'):
                new_line = "frameSize = " + segment_size
                f.write(new_line)
                f.write("\n")
            elif line.startswith('frameStep'):
                new_line = "frameStep = " + step_size + "0"
                f.write(new_line)
                f.write("\n")
            else:
                f.write(line)
    
def main(session_key, config_file, segment_size, step_size):    
    # Get audiofilename
    audio_dir = os.path.join(static_dir, "uploads", session_key)
    for file_name in os.listdir(audio_dir):
        if file_name[0] != ".":
            audio_name = file_name
            break
    # Get full path
    audio_path = os.path.join(audio_dir, file_name)

# If mp3, convert to wav
    if audio_path[-3:] == "mp3":
        #wav_audio = AudioSegment.from_mp3(audio_path)
        wav_audio = AudioSegment.from_file(audio_path)
        audio_path = audio_path[:-3:] + "wav" # set new audio_path
        wav_audio.export(audio_path, format="wav")
    
    if audio_path[-3:] == "m4a":
        #wav_audio = AudioSegment.from_mp3(audio_path)
        wav_audio = AudioSegment.from_file(audio_path)
        audio_path = audio_path[:-3:] + "wav" # set new audio_path
        wav_audio.export(audio_path, format="wav")
    
    # Get metadata
    #loaded_sound = AudioSegment.from_wav(audio_path)
    loaded_sound = AudioSegment.from_file(audio_path)
    audio_duration = len(loaded_sound)
    frame_rate = loaded_sound.frame_rate


    # If duration is longer than 1 hour, segment into chunks
    if audio_duration > 3600000:
        chunks = []
        chunk_start_time = 0
        while chunk_start_time * 1000 < audio_duration:
            subprocess.call(["sox", os.path.relpath(audio_path, os.path.join(static_dir, '..')), os.path.join(audio_dir, str(int((chunk_start_time / 3600)+1)) + ".wav"), "trim", str(chunk_start_time), "3600"])
            chunks.append(os.path.join(audio_dir, str(int((chunk_start_time / 3600)+1)) + ".wav"))
            chunk_start_time += 3600
    else:
        chunks = [os.path.relpath(audio_path, os.path.join(static_dir, '..'))]


    # Create dir for ouput and set filenames
    output_dir = os.path.join(static_dir, "data", session_key)
    subprocess.call(["mkdir", output_dir])
    output_path = os.path.join(output_dir, audio_name.split(".")[0] + ".mfcc.htk")

    if config_file == "spectrogram":
        waveform = wavfile.read(audio_path)[1]
        print(frame_rate)
        print(segment_size)
        print(int(frame_rate*segment_size))
        f, t, Sxx = signal.spectrogram(waveform, fs=frame_rate, nperseg=int(frame_rate*(segment_size/10000)), noverlap=0)
        Sxx_transpose = Sxx.transpose()
        print("scipy shape: ", Sxx_transpose.shape)

        # Reduce dimensionality to 39 with svd
        svd = TruncatedSVD(n_components=39)
        result = svd.fit_transform(Sxx_transpose)
        print("scipy shape2: ", result.shape)

    elif config_file == "multitaper":

        # Read audio file and define parameters
        sr, audio_signal = wavfile.read(audio_path)#librosa.core.load(audio_path,mono=True, sr=None)
        win_len = int(segment_size / 10)
        step_len = (segment_size / 10)

        # Multitaper spectrum and spectral slope
        numK = 5 # Number of multitaper windows
        freqlim = 500 # Threshold for high and low frequencies in slope estimation

        multitaper_spect,_ = Multitaper(sig_audio = audio_signal, ln_window_ms = win_len, step_window_ms = step_len, sr = sr, numK = numK)

        amplitude_lo, slopes_hi, slopes_lo = spectrum_slopes(spect_data = multitaper_spect, freqlim = freqlim, sr = sr, logscale = False)

        result = np.concatenate((multitaper_spect,amplitude_lo.reshape((-1,1)), slopes_lo.reshape((-1,1)), slopes_hi.reshape((-1,1))), axis = 1)
    
    elif config_file == "rastaplp":

        # Read audio file and define parameters
        sr, audio_signal = wavfile.read(audio_path)#librosa.core.load(audio_path,mono=True, sr=None)

        if len(audio_signal.shape) == 2:
            audio_signal = audio_signal[:,0]

        if type(audio_signal[0]) == np.int16:
            audio_signal = audio_signal.astype(np.float32) / 32768
        elif type(audio_signal[0]) == np.int32:
            audio_signal = audio_signal.astype(np.float32) / 2147483648

        win_len = segment_size / 10
        step_len = segment_size / 10
        num_rasta = 19

        # Extract RASTA features
        rasta_sig = rastaplp(x = audio_signal, fs = sr, win_time = win_len/1000, hop_time = step_len/1000, dorasta = True, modelorder = num_rasta - 1)

        rasta_delta = delta(rasta_sig)

        rasta_delta_delta = delta(rasta_delta)

        features = np.concatenate((rasta_sig, rasta_delta, rasta_delta_delta), axis = 0)


        result = features.T

    else:
        # Prepend path to config file
        config_file = os.path.join(config_dir, config_file)

        # Update config file with segment- and steplength, divided by 1000 to get second-format
        update_config(config_file, str(segment_size/10000), str(step_size/10000))

        # Run opensmile to output features in output dir
        print(output_path)
        subprocess.call([smilextract, "-C", config_file, "-I", audio_path, "-O", output_path])

        # Read file, and return formatted data
        htk_reader = HTKFile()
        htk_reader.load(output_path)
        result = np.array(htk_reader.data)
    
    # Flatten concatenate ten vectors at a time, resulting in 39*10 dimensionality per snippet
    new_result = []
    temp_list = []
    for vec in result:
        temp_list.append(vec)
        if len(temp_list) == 10:
            new_result.append(np.concatenate(tuple(temp_list), axis=0))
            temp_list = []
    result = np.array(new_result)
    
    # Reduce dimensionality of data under 50 dimensions for TSNE stability
    pca_reduc = PCA(n_components = 50)
    reduc_result = pca_reduc.fit_transform(result)

    # Run data through t-SNE
    tsne = TSNE(n_components=2, perplexity=25)#, random_state=None)
    Y1 = convert_range(tsne.fit_transform(reduc_result))
    print("t-SNE done")

    # Run data through PCA
    pca = PCA(n_components=2)
    Y2 = convert_range(pca.fit_transform(result))
    print("PCA done")

    # Run data through SOM
    som = True
    if som:
        print("SOM-grid-size: ", int(len(result)**0.5))
        mapsize = [int(len(result)**0.5), int(len(result)**0.5)]
        if mapsize[0] > 100:
            mapsize = [100, 100]
        som = sompy.SOMFactory.build(result, mapsize, mask=None, mapshape='planar', lattice='rect', normalization='var', initialization='pca', neighborhood='gaussian', training='batch', name='sompy')  # this will use the default parameters, but i can change the initialization and neighborhood methods
        som.train(n_job=1, verbose='info')  # verbose='debug' will print more, and verbose=None wont print anything
        som_output = np.array(np.array([np.array(np.unravel_index(int(bmu), (mapsize[0],mapsize[0]))) for bmu in som._bmu[0]]))
        Y3 = convert_range(som_output)
        print("SOM done")
    else:
        Y3 = convert_range(np.array([np.array([random.randint(-50, 50), random.randint(-50, 50)]) for i in range(len(Y2))]))

    # Run data through UMAP
    run_umap = True
    if run_umap:
        Y4 = convert_range(umap.UMAP().fit_transform(result))
        print("UMAP done")
    else:
        Y4 = convert_range(np.array([np.array([random.randint(-50, 50), random.randint(-50, 50)]) for i in range(len(Y2))]))

    # Run data through isomap
    IM = Isomap(n_components=2)
    Y5 = convert_range(IM.fit_transform(result))
    print("Isomap done")

    # Experiment with autoencoder, bad results so commented for now
    # Run data through autoencoder
    # ae = False
    # if ae:
    #     Y5 = convert_range(AE(result))
    # else:
    #     Y5 = convert_range(np.array([np.array([random.randint(-50, 50), random.randint(-50, 50)]) for i in range(len(Y2))]))
    # print("Autoencoder done")



    # K-means on raw features
    kmeans2 = KMeans(n_clusters=2, random_state=0).fit(result)
    print("kmeans2 done")
    kmeans3 = KMeans(n_clusters=3, random_state=0).fit(result)
    print("kmeans3 done")
    kmeans4 = KMeans(n_clusters=4, random_state=0).fit(result)
    print("kmeans4 done")
    kmeans5 = KMeans(n_clusters=5, random_state=0).fit(result)
    print("kmeans5 done")
    kmeans6 = KMeans(n_clusters=6, random_state=0).fit(result)
    print("kmeans6 done")
    kmeans7 = KMeans(n_clusters=7, random_state=0).fit(result)
    print("kmeans7 done")
    kmeans8 = KMeans(n_clusters=8, random_state=0).fit(result)
    print("kmeans8 done")
    kmeans20 = KMeans(n_clusters=20, random_state=0).fit(result)
    print("kmeans20 done")


    # Format t-SNE output to correct dictionary format
    data = []
    i = 0
    for coord1, coord2, coord3, coord4, coord5, cluster_index2, cluster_index3, cluster_index4, cluster_index5, cluster_index6, cluster_index7, cluster_index8, cluster_index20 in zip(Y1, Y2, Y3, Y4, Y5, kmeans2.labels_, kmeans3.labels_, kmeans4.labels_, kmeans5.labels_, kmeans6.labels_, kmeans7.labels_, kmeans8.labels_, kmeans20.labels_):
        data.append({
            "id":i, 
            "tsneX":float(coord1[0]), 
            "tsneY":float(coord1[1]), 
            "pcaX":float(coord2[0]), 
            "pcaY":float(coord2[1]), 
            "somX":float(coord3[0]), 
            "somY":float(coord3[1]), 
            "umapX":float(coord4[0]), 
            "umapY":float(coord4[1]), 
            "aeX":float(coord5[0]), 
            "aeY":float(coord5[1]), 
            "start":int(i*step_size), 
            "active":1, 
            "color":"black", 
            "kcolor2":color_dict[str(cluster_index2)], 
            "kcolor3":color_dict[str(cluster_index3)], 
            "kcolor4":color_dict[str(cluster_index4)], 
            "kcolor5":color_dict[str(cluster_index5)], 
            "kcolor6":color_dict[str(cluster_index6)], 
            "kcolor7":color_dict[str(cluster_index7)], 
            "kcolor8":color_dict[str(cluster_index8)],
            "kcolor20":color_dict[str(cluster_index20)]})
        #data.append({"id":i, "tsneX":random.randint(1,99), "tsneY":random.randint(1,99), "pcaX":random.randint(1,99), "pcaY":random.randint(1,99), "start":int(i*step_size), "active":1, "color":"black"})
        i+=1

    # Save data as csv to be able to load later
    keys = data[0].keys()
    with open(os.path.join(output_dir, "data.csv"), 'w') as output_file:
        dict_writer = csv.DictWriter(output_file, keys)
        dict_writer.writeheader()
        dict_writer.writerows(data)

    # Save metadata as csv to be able to load later
    metadata = [{"audio_duration":audio_duration, "audio_path": os.path.relpath(audio_path, os.path.join(static_dir, '..')), "segment_size":segment_size, "step_size":step_size, "chunks":",".join(chunks)}]
    keys = metadata[0].keys()
    with open(os.path.join(output_dir, "metadata.csv"), 'w') as output_file:
        dict_writer = csv.DictWriter(output_file, keys)
        dict_writer.writeheader()
        dict_writer.writerows(metadata)

    #return data, audio_duration

def retrain(valid_points, session_key, old_session_key, segment_size, step_size):    
    # Get audiofilename
    audio_dir = os.path.join(static_dir, "uploads", session_key)
    for file_name in os.listdir(audio_dir):
        if file_name[0] != ".":
            audio_name = file_name
            break
    # Get full path
    audio_path = os.path.join(audio_dir, file_name)

    # If mp3, convert to wav
    if audio_path[-3:] == "mp3":
        wav_audio = AudioSegment.from_mp3(audio_path)
        audio_path = audio_path[:-3:] + "wav" # set new audio_path
        wav_audio.export(audio_path, format="wav")
    
    # Get metadata
    audio_duration = len(AudioSegment.from_wav(audio_path))

    # Create dir for ouput and set filenames
    output_dir = os.path.join(static_dir, "data", session_key)
    subprocess.call(["mkdir", output_dir])

    # Copy audio
    path_to_old_htk = os.path.join(static_dir, "data", old_session_key, audio_name.split(".")[0] + ".mfcc.htk")
    path_to_new_htk = os.path.join(static_dir, "data", session_key, audio_name.split(".")[0] + ".mfcc.htk")
    subprocess.call(["cp", path_to_old_htk, path_to_new_htk])

    # Read file, and return formatted data
    htk_reader = HTKFile()
    htk_reader.load(path_to_old_htk)
    result = np.array(htk_reader.data)
    new_result = []
    
    valid_points_indexes = [i[0] for i in valid_points[1:]]
    start_times = [i[1] for i in valid_points[1:]]
    colors = [i[2] for i in valid_points[1:]]
    for i, line in enumerate(result):
        if i in valid_points_indexes:
            new_result.append(line)

    new_result = np.array(new_result)
    
    pca_reduc = PCA(n_components = 39)
    new_reduc_result = pca_reduc.fit_transform(new_result)

    # Run data through t-SNE
    tsne = TSNE(n_components=2, perplexity=25)#, random_state=None)
    Y1 = convert_range(tsne.fit_transform(new_reduc_result))
    print("t-SNE done")

    # Run data through PCA
    pca = PCA(n_components=2)
    Y2 = convert_range(pca.fit_transform(new_result))
    print("PCA done")

    # Run data through SOM
    som = True
    if som:
        print("SOM-grid-size: ", int(len(new_result)**0.5))
        mapsize = [int(len(new_result)**0.5), int(len(new_result)**0.5)]
        if mapsize[0] > 100:
            mapsize = [100, 100]
        som = sompy.SOMFactory.build(new_result, mapsize, mask=None, mapshape='planar', lattice='rect', normalization='var', initialization='pca', neighborhood='gaussian', training='batch', name='sompy')  # this will use the default parameters, but i can change the initialization and neighborhood methods
        som.train(n_job=1, verbose='info')  # verbose='debug' will print more, and verbose=None wont print anything
        #som_output = np.array([np.array([0, int(bmu)]) if int(bmu) < 10 else np.array([int(str(bmu)[0]), int(str(bmu)[1])]) for bmu in som._bmu[0]])
        som_output = np.array(np.array([np.array(np.unravel_index(int(bmu), (mapsize[0],mapsize[0]))) for bmu in som._bmu[0]]))
        Y3 = convert_range(som_output)
        print("SOM done")
    else:
        Y3 = convert_range(np.array([np.array([random.randint(-50, 50), random.randint(-50, 50)]) for i in range(len(Y2))]))

    # Run data through UMAP
    run_umap = True
    if run_umap:
        Y4 = convert_range(umap.UMAP().fit_transform(new_result))
        print("UMAP done")
    else:
        Y4 = convert_range(np.array([np.array([random.randint(-50, 50), random.randint(-50, 50)]) for i in range(len(Y2))]))

    # Run data through autoencoder
    ae = False
    if ae:
        Y5 = convert_range(AE(result))
    else:
        Y5 = convert_range(np.array([np.array([random.randint(-50, 50), random.randint(-50, 50)]) for i in range(len(Y2))]))
    print("Autoencoder done")

    # K-means on raw features
    kmeans2 = KMeans(n_clusters=2, random_state=0).fit(new_result)
    print("kmeans2 done")
    kmeans3 = KMeans(n_clusters=3, random_state=0).fit(new_result)
    print("kmeans3 done")
    kmeans4 = KMeans(n_clusters=4, random_state=0).fit(new_result)
    print("kmeans4 done")
    kmeans5 = KMeans(n_clusters=5, random_state=0).fit(new_result)
    print("kmeans5 done")
    kmeans6 = KMeans(n_clusters=6, random_state=0).fit(new_result)
    print("kmeans6 done")
    kmeans7 = KMeans(n_clusters=7, random_state=0).fit(new_result)
    print("kmeans7 done")
    kmeans8 = KMeans(n_clusters=8, random_state=0).fit(new_result)
    print("kmeans8 done")

    # Format t-SNE output to correct dictionary format
    data = []
    i = 0
    for coord1, coord2, coord3, coord4, coord5, start_time, color, cluster_index2, cluster_index3, cluster_index4, cluster_index5, cluster_index6, cluster_index7, cluster_index8 in zip(Y1, Y2, Y3, Y4, Y5, start_times, colors, kmeans2.labels_, kmeans3.labels_, kmeans4.labels_, kmeans5.labels_, kmeans6.labels_, kmeans7.labels_, kmeans8.labels_):
        data.append({
            "id":i, 
            "tsneX":float(coord1[0]), 
            "tsneY":float(coord1[1]), 
            "pcaX":float(coord2[0]), 
            "pcaY":float(coord2[1]), 
            "somX":float(coord3[0]), 
            "somY":float(coord3[1]), 
            "umapX":float(coord4[0]), 
            "umapY":float(coord4[1]),
            "aeX":float(coord5[0]), 
            "aeY":float(coord5[1]), 
            "start":start_time, 
            "active":1, 
            "color":color, 
            "kcolor2":color_dict[str(cluster_index2)], 
            "kcolor3":color_dict[str(cluster_index3)], 
            "kcolor4":color_dict[str(cluster_index4)], 
            "kcolor5":color_dict[str(cluster_index5)], 
            "kcolor6":color_dict[str(cluster_index6)], 
            "kcolor7":color_dict[str(cluster_index7)], 
            "kcolor8":color_dict[str(cluster_index8)]})
        #data.append({"id":i, "tsneX":random.randint(1,99), "tsneY":random.randint(1,99), "pcaX":random.randint(1,99), "pcaY":random.randint(1,99), "start":int(i*step_size), "active":1, "color":"black"})
        i+=1

    # Save data as csv to be able to load later
    keys = data[0].keys()
    with open(os.path.join(output_dir, "data.csv"), 'w') as output_file:
        dict_writer = csv.DictWriter(output_file, keys)
        dict_writer.writeheader()
        dict_writer.writerows(data)

    # Save metadata as csv to be able to load later
    metadata = [{"audio_duration":audio_duration, "audio_path": os.path.relpath(audio_path, os.path.join(static_dir, '..')), "segment_size":segment_size, "step_size":step_size}]
    keys = metadata[0].keys()
    with open(os.path.join(output_dir, "metadata.csv"), 'w') as output_file:
        dict_writer = csv.DictWriter(output_file, keys)
        dict_writer.writeheader()
        dict_writer.writerows(metadata)

def convert_range(Y):
    new_range = (80 - (-80))  
    Y_x = Y[:,0]
    
    
    old_range_x = (max(Y_x) - min(Y_x))  
    new_Y_x = (((Y_x - min(Y_x)) * new_range) / old_range_x) + (-80)

    Y_y = Y[:,1]
    old_range_y = (max(Y_y) - min(Y_y))  
    new_Y_y = (((Y_y - min(Y_y)) * new_range) / old_range_y) + (-80)
    
    return np.array((new_Y_x, new_Y_y)).T

def OA_windowing(signal, ln_window_ms, step_window_ms, sr, fn_window):
    ln_window_samples = int(ln_window_ms * sr / 1000)
    step_window_samples = int(step_window_ms * sr / 1000)

    samples_channel = signal.shape[0] # This is the case downsampled to mono, keep in mind stereo case

    total_windows = int(np.floor((samples_channel - ln_window_samples) / step_window_samples) + 1)

    sig_windowed = np.zeros((total_windows,ln_window_samples))

    idx_ini = 0
    idx_end = ln_window_samples

    pad_signal = np.concatenate((signal.reshape((1,-1)),np.zeros((1,ln_window_samples))),axis=1)

    window = np.zeros((1,ln_window_samples))

    if fn_window == "Rect":
        window = np.ones((1,ln_window_samples))
    elif fn_window == "Hann":
        window = np.hanning(ln_window_samples).reshape((1,-1))

    for i in range(total_windows):

        sig_windowed[i,:] = np.multiply(pad_signal[:,idx_ini:idx_end].reshape((1,-1)),window)

        idx_ini += step_window_samples
        idx_end += step_window_samples

    return sig_windowed

def Multitaper(sig_audio, ln_window_ms, step_window_ms, sr, numK):
    tapers = win.dpss(int(ln_window_ms * sr / 1000),NW = 3, Kmax = numK) # Use half bandwidth (NW) = 3 or 4

    windowed_rect = OA_windowing(sig_audio,ln_window_ms, step_window_ms, sr, 'Rect')

    windowed_dpss = np.zeros((windowed_rect.shape[0],int(windowed_rect.shape[1]/2 + 1),numK))

    for k in range(numK):
        windowed_dpss[:,:,1] = np.abs(np.fft.rfft(windowed_rect * tapers[k,:],axis=1))

    multitaper_spect = np.mean(windowed_dpss,axis=2)

    return multitaper_spect, windowed_dpss

def spectrum_slopes(spect_data, freqlim, sr, logscale = False):
    # Initialize parameters
    numfreq = spect_data.shape[1] # Number of frequency bands
    sample_lim = int(2 * freqlim * numfreq / sr) + 1 # index of frequency limit

    if logscale:
        spect_data = 20 * np.log10(np.abs(spect_data))

    # Divide spectrum into high and low sections
    spect_lo = spect_data[:,:sample_lim]
    spect_hi = spect_data[:,sample_lim:]

    # Calculate amplitude as difference between max and min amplitudes in low section
    amplitude_lo = np.amax(spect_lo, axis = 1) - np.amin(spect_lo, axis = 1)

    # Calculate regressive slopes
    slopes_lo = np.zeros((spect_lo.shape[0],))
    slopes_hi = np.zeros((spect_lo.shape[0],))
    for frame in range(spect_lo.shape[0]):
        slopes_lo[frame],_,_,_,_ = stats.linregress(np.arange(0,sample_lim),spect_lo[frame,:])
        slopes_hi[frame],_,_,_,_ = stats.linregress(np.arange(sample_lim,numfreq),spect_hi[frame,:])

    # Normalize slopes
    amplitude_lo = amplitude_lo / np.max(np.abs(amplitude_lo))
    slopes_lo = slopes_lo / np.max(np.abs(slopes_lo))
    slopes_hi = slopes_hi / np.max(np.abs(slopes_hi))

    return amplitude_lo, slopes_lo, slopes_hi