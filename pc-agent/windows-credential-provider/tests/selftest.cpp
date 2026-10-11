// selftest.cpp - exercises the provider's COM entry points without installing
// it or locking the workstation. Loads the DLL, instantiates the provider via
// DllGetClassObject, and drives the documented interfaces.
//
// Usage: BioUnlockProviderSelfTest.exe [path-to-BioUnlockProvider.dll]

#include <windows.h>
#include <credentialprovider.h>
#include <objbase.h>

#include <cstdio>

namespace {

const CLSID kProviderClsid = {
    0xb10f7a5e, 0x3c41, 0x4e9a, {0x9f, 0x2b, 0x7d, 0x6c, 0x1a, 0x2e, 0x3f, 0x40}};

// Field ids from Provider.h: FI_TILEIMAGE=0, FI_LABEL=1, FI_SUBMIT_BUTTON=2.
constexpr DWORD kLabelFieldId = 1;

int Fail(const wchar_t* what, HRESULT hr) {
    wprintf(L"FAIL: %ls (hr=0x%08lX)\n", what, static_cast<unsigned long>(hr));
    return 1;
}

}  // namespace

int wmain(int argc, wchar_t** argv) {
    const wchar_t* dllPath = argc > 1 ? argv[1] : L"BioUnlockProvider.dll";

    HMODULE module = LoadLibraryW(dllPath);
    if (!module) {
        wprintf(L"FAIL: LoadLibrary(%ls) error %lu\n", dllPath, GetLastError());
        return 1;
    }

    using GetClassObjectFn = HRESULT(STDAPICALLTYPE*)(REFCLSID, REFIID, void**);
    auto getClassObject =
        reinterpret_cast<GetClassObjectFn>(GetProcAddress(module, "DllGetClassObject"));
    if (!getClassObject) {
        wprintf(L"FAIL: DllGetClassObject not exported\n");
        return 1;
    }

    IClassFactory* factory = nullptr;
    HRESULT hr = getClassObject(kProviderClsid, IID_IClassFactory, reinterpret_cast<void**>(&factory));
    if (FAILED(hr)) {
        return Fail(L"DllGetClassObject", hr);
    }

    ICredentialProvider* provider = nullptr;
    hr = factory->CreateInstance(nullptr, IID_ICredentialProvider, reinterpret_cast<void**>(&provider));
    factory->Release();
    if (FAILED(hr)) {
        return Fail(L"CreateInstance(ICredentialProvider)", hr);
    }

    hr = provider->SetUsageScenario(CPUS_UNLOCK_WORKSTATION, 0);
    if (FAILED(hr)) {
        return Fail(L"SetUsageScenario", hr);
    }

    DWORD fieldCount = 0;
    hr = provider->GetFieldDescriptorCount(&fieldCount);
    if (FAILED(hr)) {
        return Fail(L"GetFieldDescriptorCount", hr);
    }
    wprintf(L"field descriptors: %lu\n", fieldCount);

    DWORD count = 0;
    DWORD defaultIndex = 0;
    BOOL autoLogon = FALSE;
    hr = provider->GetCredentialCount(&count, &defaultIndex, &autoLogon);
    if (FAILED(hr)) {
        return Fail(L"GetCredentialCount", hr);
    }
    wprintf(L"credentials: %lu (default=%lu autoLogon=%d)\n", count, defaultIndex, autoLogon);

    if (count > 0) {
        ICredentialProviderCredential* credential = nullptr;
        hr = provider->GetCredentialAt(0, &credential);
        if (FAILED(hr)) {
            return Fail(L"GetCredentialAt", hr);
        }
        PWSTR label = nullptr;
        credential->GetStringValue(kLabelFieldId, &label);
        wprintf(L"tile label: %ls\n", label ? label : L"(null)");
        if (label) {
            CoTaskMemFree(label);
        }

        CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE response = CPGSR_NO_CREDENTIAL_NOT_FINISHED;
        CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION serialization = {};
        PWSTR statusText = nullptr;
        CREDENTIAL_PROVIDER_STATUS_ICON statusIcon = CPSI_NONE;
        hr = credential->GetSerialization(&response, &serialization, &statusText, &statusIcon);
        if (FAILED(hr)) {
            return Fail(L"GetSerialization", hr);
        }
        wprintf(L"serialization: response=%d package=%lu bytes=%lu\n", response,
                serialization.ulAuthenticationPackage, serialization.cbSerialization);
        if (serialization.rgbSerialization) {
            CoTaskMemFree(serialization.rgbSerialization);
        }
        if (statusText) {
            CoTaskMemFree(statusText);
        }
        credential->Release();
    } else {
        wprintf(L"(no ticket present; provider offers no credential - expected before approval)\n");
    }

    provider->Release();
    FreeLibrary(module);
    wprintf(L"SELFTEST OK\n");
    return 0;
}
