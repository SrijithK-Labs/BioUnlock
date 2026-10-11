// Provider.cpp - BioUnlock credential provider implementation.

#include "Provider.h"

#include <cstring>

namespace {

// Fields shown on the tile. The tile image is optional but keeps the layout
// consistent with the built-in providers.
const CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR kFieldDescriptors[] = {
    {FI_TILEIMAGE, CPFT_TILE_IMAGE, const_cast<LPWSTR>(L"Image"), GUID_NULL},
    {FI_LABEL, CPFT_LARGE_TEXT, const_cast<LPWSTR>(L"BioUnlock"), GUID_NULL},
    {FI_SUBMIT_BUTTON, CPFT_SUBMIT_BUTTON, const_cast<LPWSTR>(L"Sign in"), GUID_NULL},
};

HRESULT FieldDescriptorCopy(const CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR& source,
                            CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR** ppDest) {
    auto* dest = static_cast<CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR*>(
        CoTaskMemAlloc(sizeof(CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR)));
    if (!dest) {
        return E_OUTOFMEMORY;
    }
    *dest = source;
    dest->pszLabel = nullptr;
    if (source.pszLabel) {
        HRESULT hr = SHStrDupW(source.pszLabel, &dest->pszLabel);
        if (FAILED(hr)) {
            CoTaskMemFree(dest);
            return hr;
        }
    }
    *ppDest = dest;
    return S_OK;
}

// Finds an authentication package that can validate an interactive password.
// Negotiate covers domain (Kerberos/NTLM) and local (NTLM -> MSV1_0) accounts.
HRESULT RetrieveNegotiateAuthPackage(ULONG* pulAuthPackage) {
    static ULONG cached = static_cast<ULONG>(-1);
    if (cached != static_cast<ULONG>(-1)) {
        *pulAuthPackage = cached;
        return S_OK;
    }

    HANDLE lsa = nullptr;
    if (LsaConnectUntrusted(&lsa) != 0) {
        return E_FAIL;
    }

    const char* candidates[] = {"Negotiate", "Kerberos", "MICROSOFT_AUTHENTICATION_PACKAGE_V1_0"};
    ULONG found = static_cast<ULONG>(-1);
    for (const char* name : candidates) {
        LSA_STRING packageName = {};
        packageName.Buffer = const_cast<char*>(name);
        packageName.Length = static_cast<USHORT>(strlen(name));
        packageName.MaximumLength = static_cast<USHORT>(packageName.Length + 1);
        ULONG package = 0;
        if (LsaLookupAuthenticationPackage(lsa, &packageName, &package) == 0) {
            found = package;
            break;
        }
    }
    LsaDeregisterLogonProcess(lsa);

    if (found == static_cast<ULONG>(-1)) {
        return E_FAIL;
    }
    cached = found;
    *pulAuthPackage = found;
    return S_OK;
}

void FillUnicodeString(UNICODE_STRING& target, BYTE* position, SIZE_T lengthBytes) {
    target.Buffer = reinterpret_cast<PWSTR>(position);
    target.Length = static_cast<USHORT>(lengthBytes);
    target.MaximumLength = static_cast<USHORT>(lengthBytes + sizeof(wchar_t));
}

// Packs a KERB_INTERACTIVE_(UNLOCK_)LOGON into a single CoTaskMemAlloc buffer.
HRESULT CreateSerialization(const TicketData& ticket, CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus,
                            CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION* pcpcs) {
    ULONG authPackage = 0;
    HRESULT hr = RetrieveNegotiateAuthPackage(&authPackage);
    if (FAILED(hr)) {
        return hr;
    }

    const std::wstring domain = ticket.domain.empty() ? L"." : ticket.domain;
    const std::wstring& username = ticket.username;
    const std::wstring& password = ticket.password;

    const bool unlock = (cpus == CPUS_UNLOCK_WORKSTATION);
    const SIZE_T header =
        unlock ? sizeof(KERB_INTERACTIVE_UNLOCK_LOGON) : sizeof(KERB_INTERACTIVE_LOGON);

    const SIZE_T domainBytes = domain.size() * sizeof(wchar_t);
    const SIZE_T usernameBytes = username.size() * sizeof(wchar_t);
    const SIZE_T passwordBytes = password.size() * sizeof(wchar_t);
    const SIZE_T total = header + (domainBytes + sizeof(wchar_t)) +
                         (usernameBytes + sizeof(wchar_t)) + (passwordBytes + sizeof(wchar_t));

    auto* buffer = static_cast<BYTE*>(CoTaskMemAlloc(total));
    if (!buffer) {
        return E_OUTOFMEMORY;
    }
    ZeroMemory(buffer, total);

    BYTE* domainPos = buffer + header;
    BYTE* usernamePos = domainPos + domainBytes + sizeof(wchar_t);
    BYTE* passwordPos = usernamePos + usernameBytes + sizeof(wchar_t);
    memcpy(domainPos, domain.c_str(), domainBytes);
    memcpy(usernamePos, username.c_str(), usernameBytes);
    memcpy(passwordPos, password.c_str(), passwordBytes);

    if (unlock) {
        auto* kiul = reinterpret_cast<KERB_INTERACTIVE_UNLOCK_LOGON*>(buffer);
        kiul->Logon.MessageType = KerbWorkstationUnlockLogon;
        FillUnicodeString(kiul->Logon.LogonDomainName, domainPos, domainBytes);
        FillUnicodeString(kiul->Logon.UserName, usernamePos, usernameBytes);
        FillUnicodeString(kiul->Logon.Password, passwordPos, passwordBytes);
        kiul->LogonId.LowPart = 0;
        kiul->LogonId.HighPart = 0;
    } else {
        auto* kil = reinterpret_cast<KERB_INTERACTIVE_LOGON*>(buffer);
        kil->MessageType = KerbInteractiveLogon;
        FillUnicodeString(kil->LogonDomainName, domainPos, domainBytes);
        FillUnicodeString(kil->UserName, usernamePos, usernameBytes);
        FillUnicodeString(kil->Password, passwordPos, passwordBytes);
    }

    pcpcs->rgbSerialization = buffer;
    pcpcs->cbSerialization = static_cast<ULONG>(total);
    pcpcs->ulAuthenticationPackage = authPackage;
    pcpcs->clsidCredentialProvider = CLSID_BioUnlockProvider;
    return S_OK;
}

}  // namespace

// ---------------------------------------------------------------------------
// CBioUnlockProvider
// ---------------------------------------------------------------------------

CBioUnlockProvider::CBioUnlockProvider()
    : _cRef(1),
      _cpus(CPUS_INVALID),
      _pEvents(nullptr),
      _upAdviseContext(0),
      _state(std::make_shared<ProviderState>()) {
    DllAddRef();
}

CBioUnlockProvider::~CBioUnlockProvider() {
    StopWatcher();
    if (_pEvents) {
        _pEvents->Release();
    }
    DllRelease();
}

IFACEMETHODIMP CBioUnlockProvider::QueryInterface(REFIID riid, void** ppv) {
    if (!ppv) {
        return E_POINTER;
    }
    *ppv = nullptr;
    if (riid == IID_IUnknown || riid == IID_ICredentialProvider) {
        *ppv = static_cast<ICredentialProvider*>(this);
    } else if (riid == IID_ICredentialProviderSetUserArray) {
        *ppv = static_cast<ICredentialProviderSetUserArray*>(this);
    } else {
        return E_NOINTERFACE;
    }
    AddRef();
    return S_OK;
}

IFACEMETHODIMP_(ULONG) CBioUnlockProvider::AddRef() {
    return InterlockedIncrement(&_cRef);
}

IFACEMETHODIMP_(ULONG) CBioUnlockProvider::Release() {
    LONG count = InterlockedDecrement(&_cRef);
    if (count == 0) {
        delete this;
    }
    return count;
}

IFACEMETHODIMP CBioUnlockProvider::SetUsageScenario(CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus,
                                                    DWORD /*dwFlags*/) {
    _cpus = cpus;
    return S_OK;
}

IFACEMETHODIMP CBioUnlockProvider::SetSerialization(
    const CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION* /*pcpcs*/) {
    return S_OK;
}

IFACEMETHODIMP CBioUnlockProvider::Advise(ICredentialProviderEvents* pcpe,
                                          UINT_PTR upAdviseContext) {
    _pEvents = pcpe;
    if (_pEvents) {
        _pEvents->AddRef();
    }
    _upAdviseContext = upAdviseContext;
    StartWatcher();
    return S_OK;
}

IFACEMETHODIMP CBioUnlockProvider::UnAdvise() {
    StopWatcher();
    if (_pEvents) {
        _pEvents->Release();
        _pEvents = nullptr;
    }
    return S_OK;
}

IFACEMETHODIMP CBioUnlockProvider::GetFieldDescriptorCount(DWORD* pdwCount) {
    if (!pdwCount) {
        return E_POINTER;
    }
    *pdwCount = FI_NUM_FIELDS;
    return S_OK;
}

IFACEMETHODIMP CBioUnlockProvider::GetFieldDescriptorAt(
    DWORD dwIndex, CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR** ppcpfd) {
    if (!ppcpfd) {
        return E_POINTER;
    }
    *ppcpfd = nullptr;
    if (dwIndex >= FI_NUM_FIELDS) {
        return E_INVALIDARG;
    }
    return FieldDescriptorCopy(kFieldDescriptors[dwIndex], ppcpfd);
}

IFACEMETHODIMP CBioUnlockProvider::GetCredentialCount(DWORD* pdwCount, DWORD* pdwDefault,
                                                      BOOL* pbAutoLogonWithDefault) {
    if (!pdwCount || !pdwDefault || !pbAutoLogonWithDefault) {
        return E_POINTER;
    }
    // Only offer a credential when the phone has actually approved an unlock.
    const bool haveTicket = _state->Snapshot().has_value();
    if (haveTicket && (_cpus == CPUS_UNLOCK_WORKSTATION || _cpus == CPUS_LOGON)) {
        *pdwCount = 1;
        *pdwDefault = 0;
        *pbAutoLogonWithDefault = TRUE;
    } else {
        *pdwCount = 0;
        *pdwDefault = CREDENTIAL_PROVIDER_NO_DEFAULT;
        *pbAutoLogonWithDefault = FALSE;
    }
    return S_OK;
}

IFACEMETHODIMP CBioUnlockProvider::GetCredentialAt(DWORD dwIndex,
                                                   ICredentialProviderCredential** ppcpc) {
    if (!ppcpc) {
        return E_POINTER;
    }
    *ppcpc = nullptr;
    if (dwIndex != 0 || !_state->Snapshot().has_value()) {
        return E_INVALIDARG;
    }
    auto* credential = new (std::nothrow) CBioUnlockCredential(_state, _cpus);
    if (!credential) {
        return E_OUTOFMEMORY;
    }
    *ppcpc = credential;
    return S_OK;
}

IFACEMETHODIMP CBioUnlockProvider::SetUserArray(ICredentialProviderUserArray* /*users*/) {
    return S_OK;
}

void CBioUnlockProvider::StartWatcher() {
    if (_watcher.joinable()) {
        return;
    }
    _state->stopping = false;
    _watcher = std::thread([this] { WatcherLoop(); });
}

void CBioUnlockProvider::StopWatcher() {
    _state->stopping = true;
    if (_watcher.joinable()) {
        _watcher.join();
    }
}

void CBioUnlockProvider::WatcherLoop() {
    bool lastPresent = false;
    while (!_state->stopping.load()) {
        try {
            auto ticket = ReadUnlockTicket();
            const bool present = ticket.has_value();
            {
                std::lock_guard<std::mutex> lock(_state->mutex);
                _state->ticket = ticket;
            }
            if (present != lastPresent) {
                lastPresent = present;
                if (_pEvents) {
                    _pEvents->CredentialsChanged(_upAdviseContext);
                }
            }
        } catch (...) {
            // Never let an exception unwind across the thread; LogonUI must not crash.
        }
        for (int i = 0; i < 10 && !_state->stopping.load(); ++i) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
    }
}

// ---------------------------------------------------------------------------
// CBioUnlockCredential
// ---------------------------------------------------------------------------

CBioUnlockCredential::CBioUnlockCredential(std::shared_ptr<ProviderState> state,
                                           CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus)
    : _cRef(1), _state(std::move(state)), _cpus(cpus), _pEvents(nullptr) {
    DllAddRef();
}

CBioUnlockCredential::~CBioUnlockCredential() {
    if (_pEvents) {
        _pEvents->Release();
    }
    DllRelease();
}

IFACEMETHODIMP CBioUnlockCredential::QueryInterface(REFIID riid, void** ppv) {
    if (!ppv) {
        return E_POINTER;
    }
    *ppv = nullptr;
    if (riid == IID_IUnknown || riid == IID_ICredentialProviderCredential) {
        *ppv = static_cast<ICredentialProviderCredential*>(this);
        AddRef();
        return S_OK;
    }
    return E_NOINTERFACE;
}

IFACEMETHODIMP_(ULONG) CBioUnlockCredential::AddRef() {
    return InterlockedIncrement(&_cRef);
}

IFACEMETHODIMP_(ULONG) CBioUnlockCredential::Release() {
    LONG count = InterlockedDecrement(&_cRef);
    if (count == 0) {
        delete this;
    }
    return count;
}

IFACEMETHODIMP CBioUnlockCredential::Advise(ICredentialProviderCredentialEvents* pcpce) {
    _pEvents = pcpce;
    if (_pEvents) {
        _pEvents->AddRef();
    }
    return S_OK;
}

IFACEMETHODIMP CBioUnlockCredential::UnAdvise() {
    if (_pEvents) {
        _pEvents->Release();
        _pEvents = nullptr;
    }
    return S_OK;
}

IFACEMETHODIMP CBioUnlockCredential::SetSelected(BOOL* pbAutoLogon) {
    if (pbAutoLogon) {
        *pbAutoLogon = FALSE;
    }
    return S_OK;
}

IFACEMETHODIMP CBioUnlockCredential::SetDeselected() {
    return S_OK;
}

IFACEMETHODIMP CBioUnlockCredential::GetFieldState(
    DWORD dwFieldID, CREDENTIAL_PROVIDER_FIELD_STATE* pcpfs,
    CREDENTIAL_PROVIDER_FIELD_INTERACTIVE_STATE* pcpfis) {
    if (!pcpfs || !pcpfis) {
        return E_POINTER;
    }
    switch (dwFieldID) {
        case FI_TILEIMAGE:
        case FI_LABEL:
            *pcpfs = CPFS_DISPLAY_IN_BOTH;
            break;
        case FI_SUBMIT_BUTTON:
            *pcpfs = CPFS_DISPLAY_IN_SELECTED_TILE;
            break;
        default:
            return E_INVALIDARG;
    }
    *pcpfis = CPFIS_NONE;
    return S_OK;
}

IFACEMETHODIMP CBioUnlockCredential::GetStringValue(DWORD dwFieldID, PWSTR* ppwsz) {
    if (!ppwsz) {
        return E_POINTER;
    }
    *ppwsz = nullptr;
    switch (dwFieldID) {
        case FI_LABEL: {
            const bool haveTicket = _state->Snapshot().has_value();
            return SHStrDupW(haveTicket ? L"Unlock approved on your phone"
                                        : L"Unlock with BioUnlock",
                             ppwsz);
        }
        case FI_TILEIMAGE:
            return SHStrDupW(L"", ppwsz);
        case FI_SUBMIT_BUTTON:
            return SHStrDupW(L"Sign in", ppwsz);
        default:
            return E_INVALIDARG;
    }
}

IFACEMETHODIMP CBioUnlockCredential::GetBitmapValue(DWORD dwFieldID, HBITMAP* phbmp) {
    if (!phbmp) {
        return E_POINTER;
    }
    *phbmp = nullptr;
    if (dwFieldID == FI_TILEIMAGE) {
        return S_OK;
    }
    return E_INVALIDARG;
}

IFACEMETHODIMP CBioUnlockCredential::GetCheckboxValue(DWORD, BOOL*, PWSTR*) {
    return E_NOTIMPL;
}

IFACEMETHODIMP CBioUnlockCredential::GetSubmitButtonValue(DWORD dwFieldID, DWORD* pdwAdjacentTo) {
    if (!pdwAdjacentTo) {
        return E_POINTER;
    }
    if (dwFieldID != FI_SUBMIT_BUTTON) {
        return E_INVALIDARG;
    }
    *pdwAdjacentTo = FI_LABEL;
    return S_OK;
}

IFACEMETHODIMP CBioUnlockCredential::GetComboBoxValueCount(DWORD, DWORD*, DWORD*) {
    return E_NOTIMPL;
}

IFACEMETHODIMP CBioUnlockCredential::GetComboBoxValueAt(DWORD, DWORD, PWSTR*) {
    return E_NOTIMPL;
}

IFACEMETHODIMP CBioUnlockCredential::SetStringValue(DWORD, PCWSTR) {
    return E_NOTIMPL;
}

IFACEMETHODIMP CBioUnlockCredential::SetCheckboxValue(DWORD, BOOL) {
    return E_NOTIMPL;
}

IFACEMETHODIMP CBioUnlockCredential::SetComboBoxSelectedValue(DWORD, DWORD) {
    return E_NOTIMPL;
}

IFACEMETHODIMP CBioUnlockCredential::CommandLinkClicked(DWORD) {
    return E_NOTIMPL;
}

IFACEMETHODIMP CBioUnlockCredential::GetSerialization(
    CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE* pcpgsr,
    CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION* pcpcs, PWSTR* ppwszOptionalStatusText,
    CREDENTIAL_PROVIDER_STATUS_ICON* pcpsiOptionalStatusIcon) {
    if (!pcpgsr || !pcpcs) {
        return E_POINTER;
    }
    *pcpgsr = CPGSR_NO_CREDENTIAL_NOT_FINISHED;
    if (ppwszOptionalStatusText) {
        *ppwszOptionalStatusText = nullptr;
    }
    if (pcpsiOptionalStatusIcon) {
        *pcpsiOptionalStatusIcon = CPSI_NONE;
    }

    auto ticket = _state->Snapshot();
    if (!ticket) {
        if (ppwszOptionalStatusText) {
            SHStrDupW(L"Open BioUnlock on your phone and approve this PC.", ppwszOptionalStatusText);
        }
        if (pcpsiOptionalStatusIcon) {
            *pcpsiOptionalStatusIcon = CPSI_WARNING;
        }
        return S_OK;
    }

    HRESULT hr = CreateSerialization(*ticket, _cpus, pcpcs);
    if (FAILED(hr)) {
        if (ppwszOptionalStatusText) {
            SHStrDupW(L"BioUnlock could not prepare the credential.", ppwszOptionalStatusText);
        }
        if (pcpsiOptionalStatusIcon) {
            *pcpsiOptionalStatusIcon = CPSI_ERROR;
        }
        return S_OK;
    }

    *pcpgsr = CPGSR_RETURN_CREDENTIAL_FINISHED;
    return S_OK;
}

IFACEMETHODIMP CBioUnlockCredential::ReportResult(
    NTSTATUS /*ntsStatus*/, NTSTATUS /*ntsSubstatus*/, PWSTR* ppwszOptionalStatusText,
    CREDENTIAL_PROVIDER_STATUS_ICON* pcpsiOptionalStatusIcon) {
    if (ppwszOptionalStatusText) {
        *ppwszOptionalStatusText = nullptr;
    }
    if (pcpsiOptionalStatusIcon) {
        *pcpsiOptionalStatusIcon = CPSI_NONE;
    }
    return S_OK;
}
