// Common.h - shared definitions for the BioUnlock Credential Provider.
#pragma once

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif

#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0A00
#endif

#include <windows.h>
#include <credentialprovider.h>
#include <ntsecapi.h>
#include <wincred.h>
#include <dpapi.h>
#include <shlobj.h>
#include <shlwapi.h>
#include <objbase.h>

#include <atomic>
#include <chrono>
#include <cstdint>
#include <memory>
#include <mutex>
#include <new>
#include <optional>
#include <string>
#include <thread>
#include <vector>

// {B10F7A5E-3C41-4E9A-9F2B-7D6C1A2E3F40}
inline const CLSID CLSID_BioUnlockProvider = {
    0xb10f7a5e, 0x3c41, 0x4e9a, {0x9f, 0x2b, 0x7d, 0x6c, 0x1a, 0x2e, 0x3f, 0x40}};

#define BIOUNLOCK_PROVIDER_FRIENDLY_NAME L"BioUnlock"

// %ProgramData%\BioUnlock is the directory shared with the Python agent. The
// agent writes a short-lived, machine-DPAPI protected ticket here; this provider
// (running as SYSTEM on the secure desktop) is the only consumer.
#define BIOUNLOCK_TICKET_FILENAME L"unlock_ticket.bin"

extern HINSTANCE g_hInstance;

// Keeps the DLL loaded while COM objects are alive.
void DllAddRef();
void DllRelease();
