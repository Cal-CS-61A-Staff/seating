def arr_to_dict(arr, key_getter=lambda x: x):
    """
    Convert an array to a dictionary, grouping by the key returned by key_getter.
    """
    from collections import defaultdict
    dic = defaultdict(list)
    for x in arr:
        dic[key_getter(x)].append(x)
    return dic
