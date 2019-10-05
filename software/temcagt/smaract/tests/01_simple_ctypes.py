#!/opt/pym32/bin/python

import ctypes

print "WARNING: this uses the old (depreciated) api"

lib = ctypes.cdll.LoadLibrary('libmcscontrol.so')

#dll_version = ctypes.pointer(ctypes.c_uint(0))
dll_version = ctypes.c_uint(0)
r = lib.SA_GetDLLVersion(ctypes.byref(dll_version))
print r, dll_version.value

#n_systems = ctypes.pointer(ctypes.c_uint(0))
n_systems = ctypes.c_uint(0)
r = lib.SA_GetNumberOfSystems(ctypes.byref(n_systems))
print r, n_systems.value

#id_list = ctypes.pointer(ctypes.c_uint(0))
#id_list_size = ctypes.pointer(ctypes.c_uint(0))
id_list = ctypes.c_uint(0)
id_list_size = ctypes.c_uint(0)
r = lib.SA_GetAvailableSystems(
    ctypes.byref(id_list), ctypes.byref(id_list_size))
print r, id_list.value, id_list_size.value
