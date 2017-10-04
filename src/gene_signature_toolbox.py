"""
@author: The KnowEnG dev team
"""
import os
import numpy as np
import pandas as pd
import knpackage.toolbox as kn
import knpackage.distributed_computing_utils as dstutil

from   sklearn.metrics import silhouette_score
from   sklearn.metrics.pairwise import cosine_similarity
from   scipy.stats              import spearmanr

def run_similarity(run_parameters):
    """ Performs similarity analysis and saves  results.

    Args:
        run_parameters: parameter set dictionary.
    """

    expression_name     = run_parameters["spreadsheet_name_full_path"]
    signature_name      = run_parameters["signature_name_full_path"  ]
    similarity_measure  = run_parameters["similarity_measure"        ]

    expression_df       = kn.get_spreadsheet_df(expression_name)
    signature_df        = kn.get_spreadsheet_df(signature_name )

    samples_names       = expression_df.columns
    signatures_names    =  signature_df.columns

    similarity_mat = generate_similarity_mat(expression_df, signature_df,similarity_measure)
    similarity_mat = map_similarity_range(similarity_mat, 0)
    similarity_df  = pd.DataFrame(similarity_mat, index=samples_names, columns=signatures_names)

    save_final_samples_signature(similarity_df, run_parameters)


def run_cc_similarity(run_parameters):
    """ wrapper: call sequence to perform signature analysis with
        consensus clustering and write results.

    Args:
        run_parameters: parameter set dictionary.
    """
    tmp_dir = 'tmp_cc_similarity'
    run_parameters = update_tmp_directory(run_parameters, tmp_dir)

    expression_name      = run_parameters["spreadsheet_name_full_path"]
    signature_name       = run_parameters["signature_name_full_path"  ]
    similarity_measure   = run_parameters["similarity_measure"        ]
    number_of_bootstraps = run_parameters['number_of_bootstraps'      ]
    processing_method    = run_parameters['processing_method'         ]

    expression_df       = kn.get_spreadsheet_df(expression_name)
    signature_df        = kn.get_spreadsheet_df(signature_name )

    expression_mat      = expression_df.as_matrix()
    signature_mat       =  signature_df.as_matrix()

    if processing_method == 'serial':
        for sample in range(0, number_of_bootstraps):
            run_cc_similarity_signature_worker(expression_mat, signature_mat, run_parameters, sample)
    elif processing_method == 'parallel':
        find_and_save_cc_similarity_signature_parallel(spreadsheet_mat, run_parameters, number_of_bootstraps)
    else:
        raise ValueError('processing_method contains bad value.')

    consensus_df = form_consensus_df(run_parameters, expression_df, signature_df)
    save_final_samples_signature(consensus_df, run_parameters)

    kn.remove_dir(run_parameters["tmp_directory"])

def run_net_similarity(run_parameters):
    """ Run random walk first to smooth spreadsheet
    and perform similarity analysis and saves results.

    Args:
        run_parameters: parameter set dictionary.
    """
    expression_name     = run_parameters["spreadsheet_name_full_path"]
    signature_name      = run_parameters["signature_name_full_path"  ]
    gg_network_name     = run_parameters['gg_network_name_full_path' ]
    similarity_measure  = run_parameters["similarity_measure"        ]

    expression_df       = kn.get_spreadsheet_df(expression_name)
    signature_df        = kn.get_spreadsheet_df(signature_name )

    samples_names       = expression_df.columns
    signatures_names    =  signature_df.columns

    network_mat, unique_gene_names = kn.get_sparse_network_matrix(gg_network_name)
    network_mat                    = kn.normalize_sparse_mat_by_diagonal(network_mat)
    
    expression_df                  = kn.update_spreadsheet_df(expression_df, unique_gene_names)
    signature_df                   = kn.update_spreadsheet_df(signature_df, unique_gene_names)

    expression_mat                 = expression_df.as_matrix()
    signature_mat                  = signature_df.as_matrix()

    expression_mat, iterations = kn.smooth_matrix_with_rwr(expression_mat, network_mat, run_parameters)
    signature_mat,  iterations = kn.smooth_matrix_with_rwr(signature_mat,  network_mat, run_parameters)

    expression_df.iloc[:] = expression_mat
    signature_df.iloc[:]  = signature_mat

    similarity_mat = generate_similarity_mat(expression_df, signature_df,similarity_measure)
    similarity_mat = map_similarity_range(similarity_mat, 0)
    similarity_df  = pd.DataFrame(similarity_mat, index=samples_names, columns=signatures_names)

    save_final_samples_signature(similarity_df, run_parameters)

def run_cc_net_similarity(run_parameters):
    """ wrapper: call sequence to perform signature analysis with
        random walk smoothing and consensus clustering and write results.

    Args:
        run_parameters: parameter set dictionary.
    """
    tmp_dir = 'tmp_cc_similarity'
    run_parameters = update_tmp_directory(run_parameters, tmp_dir)

    expression_name      = run_parameters["spreadsheet_name_full_path"]
    signature_name       = run_parameters["signature_name_full_path"  ]
    gg_network_name      = run_parameters['gg_network_name_full_path' ]
    similarity_measure   = run_parameters["similarity_measure"        ]
    number_of_bootstraps = run_parameters['number_of_bootstraps'      ]
    processing_method    = run_parameters['processing_method'         ]

    expression_df        = kn.get_spreadsheet_df(expression_name)
    signature_df         = kn.get_spreadsheet_df(signature_name )

    samples_names        = expression_df.columns
    signatures_names     =  signature_df.columns

    network_mat, unique_gene_names = kn.get_sparse_network_matrix(gg_network_name)
    network_mat                    = kn.normalize_sparse_mat_by_diagonal(network_mat)
    
    expression_df                  = kn.update_spreadsheet_df(expression_df, unique_gene_names)
    signature_df                   = kn.update_spreadsheet_df(signature_df, unique_gene_names)

    expression_mat                 = expression_df.as_matrix()
    signature_mat                  = signature_df.as_matrix()

    expression_mat, iterations = kn.smooth_matrix_with_rwr(expression_mat, network_mat, run_parameters)
    signature_mat,  iterations = kn.smooth_matrix_with_rwr(signature_mat,  network_mat, run_parameters)

    expression_df.iloc[:] = expression_mat
    signature_df.iloc[:]  = signature_mat


    if processing_method == 'serial':
        for sample in range(0, number_of_bootstraps):
            run_cc_similarity_signature_worker(expression_mat, signature_mat, run_parameters, sample)
    elif processing_method == 'parallel':
        find_and_save_cc_similarity_signature_parallel(spreadsheet_mat, run_parameters, number_of_bootstraps)
    else:
        raise ValueError('processing_method contains bad value.')

    consensus_df = form_consensus_df(run_parameters, expression_df, signature_df)
    save_final_samples_signature(consensus_df, run_parameters)

    kn.remove_dir(run_parameters["tmp_directory"])


def find_and_save_cc_similarity_signature_parallel(spreadsheet_mat, run_parameters, local_parallelism):
    """ central loop: compute components for the consensus matrix by
        non-negative matrix factorization.

    Args:
        spreadsheet_mat: genes x samples matrix.
        run_parameters: dictionary of run-time parameters.
        local_parallelism: parallelism option
    """
    import knpackage.distributed_computing_utils as dstutil

    jobs_id          = range(0, local_parallelism)
    zipped_arguments = dstutil.zip_parameters(spreadsheet_mat, run_parameters, jobs_id)

    if 'parallelism' in run_parameters:
        parallelism = dstutil.determine_parallelism_locally(local_parallelism, run_parameters['parallelism'])
    else:
        parallelism = dstutil.determine_parallelism_locally(local_parallelism)

    dstutil.parallelize_processes_locally(run_cc_similarity_signature_worker, zipped_arguments, parallelism)


def run_cc_similarity_signature_worker(expression_mat, signature_mat, run_parameters, sample):
    """Worker to execute nmf_clusters in a single process

    Args:
        expression_mat: genes x samples matrix.
        signature_mat: genes x samples matrix.
        run_parameters: dictionary of run-time parameters.
        sample: each loops.

    Returns:
        None

    """
    import knpackage.toolbox as kn
    import numpy as np

    np.random.seed(sample)
    rows_sampling_fraction = run_parameters["rows_sampling_fraction"]
    cols_sampling_fraction = run_parameters["cols_sampling_fraction"]
    expression_mat_T, sample_permutation_e = kn.sample_a_matrix( expression_mat.T
                                                               , rows_sampling_fraction
                                                               , cols_sampling_fraction )
    
    signature_mat_T, sample_permutation_s = kn.sample_a_matrix( signature_mat.T 
                                                              , rows_sampling_fraction
                                                              , cols_sampling_fraction )

    save_a_signature_to_tmp(expression_mat_T.T, sample_permutation_e, signature_mat_T.T, sample_permutation_s, run_parameters, sample)


def save_a_signature_to_tmp(expression_mat, sample_permutation_e, signature_mat, sample_permutation_s, run_parameters, sequence_number):
    """ save one h_matrix and one permutation in temorary files with sequence_number appended names.

    Args:
        expression_mat: permutation x k size matrix.
        sample_permutation_e: indices of expression_mat rows permutation.
        signature_mat: permutation x k size matrix.
        sample_permutation_s: indices of signature_mat rows permutation.
        run_parameters: parmaeters including the "tmp_directory" name.
        sequence_number: temporary file name suffix.
    """
    import os
    import numpy as np

    tmp_dir = run_parameters["tmp_directory"]

    os.makedirs(tmp_dir, mode=0o755, exist_ok=True)

    hname_e = os.path.join(tmp_dir, 'tmp_h_e_%d'%(sequence_number))
    pname_e = os.path.join(tmp_dir, 'tmp_p_e_%d'%(sequence_number))

    hname_s = os.path.join(tmp_dir, 'tmp_h_s_%d'%(sequence_number))
    pname_s = os.path.join(tmp_dir, 'tmp_p_s_%d'%(sequence_number))

    with open(hname_e, 'wb') as fh0:
        expression_mat.dump(fh0)
    with open(pname_e, 'wb') as fh1:
        sample_permutation_e.dump(fh1)
    with open(hname_s, 'wb') as fh2:
        signature_mat.dump(fh2)
    with open(pname_s, 'wb') as fh3:
        sample_permutation_s.dump(fh3)


def form_consensus_df(run_parameters, expression_df_orig, signature_df_orig):
    """ compute the consensus df from the express dataframe and signature dataframe
        formed by the bootstrap "temp_*" files.

    Args:
        run_parameters: parameter set dictionary with "tmp_directory" key.
        expression_df_orig: dataframe of expression data.
        signature_df_orig: dataframe of signature data.

    Returns:
        similarity_df: similarity_df with the value to be consensus matrix
    """

    processing_method     = run_parameters['processing_method'    ]
    tmp_directory         = run_parameters['tmp_directory'        ]
    cluster_shared_volumn = run_parameters['cluster_shared_volumn']
    number_of_bootstraps  = run_parameters['number_of_bootstraps' ]
    similarity_measure    = run_parameters['similarity_measure'   ]

    if processing_method == 'distribute':
        tmp_dir = os.path.join(cluster_shared_volumn,
                               os.path.basename(os.path.normpath(tmp_directory)))
    else:
        tmp_dir = tmp_directory
        
    dir_list         = os.listdir(tmp_dir)
    samples_names    = expression_df_orig.columns
    signatures_names =  signature_df_orig.columns
    similarity_array = np.zeros((samples_names.shape[0], signatures_names.shape[0]))

    for tmp_f in dir_list:
        if tmp_f[0:8] == 'tmp_p_e_':
            pname_e = os.path.join(tmp_dir, tmp_f)
            hname_e = os.path.join(tmp_dir, 'tmp_h_e_' + tmp_f[8:len(tmp_f)])
            pname_s = os.path.join(tmp_dir, 'tmp_p_s_' + tmp_f[8:len(tmp_f)])
            hname_s = os.path.join(tmp_dir, 'tmp_h_s_' + tmp_f[8:len(tmp_f)])

            expression_mat       = np.load(hname_e)
            signature_mat        = np.load(hname_s)
            sample_permutation_e = np.load(pname_e)
            sample_permutation_s = np.load(pname_s)

            expression_df         = pd.DataFrame(expression_mat)
            expression_df.index   = expression_df_orig.index[sample_permutation_e]
            expression_df.columns = expression_df_orig.columns
            
            signature_df          = pd.DataFrame(signature_mat)
            signature_df.index    = signature_df_orig.index[sample_permutation_s]
            signature_df.columns  = signature_df_orig.columns

            similarity_mat    = generate_similarity_mat(expression_df, signature_df, similarity_measure)
            similarity_array += similarity_mat

    similarity_array /= number_of_bootstraps
    similarity_array  = map_similarity_range(similarity_array, 0)
    similarity_df     = pd.DataFrame(similarity_array, index=samples_names, columns=signatures_names)

    return similarity_df

def generate_similarity_mat(expression_df, signature_df,similarity_measure):
    """generate matrix which save the similarity value of input dataframes

    Args:
        expression_df: genes x samples dataframe.
        signature_df:  genes x samples dataframe.
        
    Returns:
        similarity_mat: matrix with similarity values
    """

    genes_in_expression =  expression_df.index
    genes_in_signature  =   signature_df.index

    common_genes        = kn.find_common_node_names(genes_in_expression, genes_in_signature)
    expression_mat      = expression_df.loc[common_genes, :].values
    signature_mat       =  signature_df.loc[common_genes, :].values
    nx                  = expression_mat.shape[1]

    if   (similarity_measure == "cosine" ):
          similarity_mat      = cosine_similarity(expression_mat.T, signature_mat.T)
    elif (similarity_measure == "spearman"):
          similarity_mat      = spearmanr(expression_mat, signature_mat)[0]
          similarity_mat      = np.abs(similarity_mat[0:nx,nx:] )

    return similarity_mat

def map_similarity_range(similarity_mat, axis_val):
    """Normalize similarity matrix via given axis

    Args:
        similarity_mat: sample1 x sample2 matrix.
        axis_val: given axis.
        
    Returns:
        similarity_mat: normalized similarity matrix with 0 and 1.
    """
    max_value_row_index = np.argmax(similarity_mat, axis=axis_val)
    num_of_cols         =  len(similarity_mat[0])

    similarity_mat[max_value_row_index, range(num_of_cols)] = 1
    similarity_mat[similarity_mat!=1]                       = 0

    return similarity_mat

def save_final_samples_signature(result_df, run_parameters):
    """ wtite .tsv file that assings a cluster number label to the sample_names.

    Args:
        result_df: result dataframe
        run_parameters: write path (run_parameters["results_directory"]).
    """
    result_df.to_csv(get_output_file_name(run_parameters, 'result', 'viz'), sep='\t')

def get_output_file_name(run_parameters, prefix_string, suffix_string='', type_suffix='tsv'):
    """ get the full directory / filename for writing
    Args:
        run_parameters: dictionary with keys: "results_directory", "method" and "correlation_measure"
        prefix_string:  the first letters of the ouput file name
        suffix_string:  the last letters of the output file name before '.tsv'

    Returns:
        output_file_name:   full file and directory name suitable for file writing
    """
    results_directory  = run_parameters["results_directory" ]
    method             = run_parameters['method'            ]
    similarity_measure = run_parameters['similarity_measure']
    output_file_name = os.path.join(results_directory, prefix_string + '_' + method + '_' + similarity_measure)
    output_file_name = kn.create_timestamped_filename(output_file_name) + '_' + suffix_string + '.' + type_suffix

    return output_file_name


def update_tmp_directory(run_parameters, tmp_dir):
    ''' Update tmp_directory value in rum_parameters dictionary

    Args:
        run_parameters: run_parameters as the dictionary config
        tmp_dir: temporary directory prefix subjected to different functions

    Returns:
        run_parameters: an updated run_parameters

    '''
    processing_method     = run_parameters['processing_method'    ]
    cluster_shared_volumn = run_parameters['cluster_shared_volumn']
    run_directory         = run_parameters["run_directory"        ]

    if processing_method == 'distribute':
        run_parameters["tmp_directory"] = kn.create_dir(cluster_shared_volumn, tmp_dir)
    else:
        run_parameters["tmp_directory"] = kn.create_dir(run_directory, tmp_dir)

    return run_parameters

