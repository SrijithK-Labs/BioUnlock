// dllmain.cpp - COM plumbing for the BioUnlock Credential Provider.

#include "Common.h"
#include "Provider.h"

HINSTANCE g_hInstance = nullptr;
static LONG g_cDllRef = 0;

void DllAddRef() {
    InterlockedIncrement(&g_cDllRef);
}

void DllRelease() {
    InterlockedDecrement(&g_cDllRef);
}

namespace {

class CClassFactory : public IClassFactory {
  public:
    CClassFactory() : _cRef(1) {
        DllAddRef();
    }

    IFACEMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (!ppv) {
            return E_POINTER;
        }
        *ppv = nullptr;
        if (riid == IID_IUnknown || riid == IID_IClassFactory) {
            *ppv = static_cast<IClassFactory*>(this);
            AddRef();
            return S_OK;
        }
        return E_NOINTERFACE;
    }

    IFACEMETHODIMP_(ULONG) AddRef() override {
        return InterlockedIncrement(&_cRef);
    }

    IFACEMETHODIMP_(ULONG) Release() override {
        LONG count = InterlockedDecrement(&_cRef);
        if (count == 0) {
            delete this;
        }
        return count;
    }

    IFACEMETHODIMP CreateInstance(IUnknown* pUnkOuter, REFIID riid, void** ppv) override {
        if (pUnkOuter) {
            return CLASS_E_NOAGGREGATION;
        }
        auto* provider = new (std::nothrow) CBioUnlockProvider();
        if (!provider) {
            return E_OUTOFMEMORY;
        }
        HRESULT hr = provider->QueryInterface(riid, ppv);
        provider->Release();
        return hr;
    }

    IFACEMETHODIMP LockServer(BOOL fLock) override {
        if (fLock) {
            DllAddRef();
        } else {
            DllRelease();
        }
        return S_OK;
    }

  private:
    ~CClassFactory() {
        DllRelease();
    }
    LONG _cRef;
};

}  // namespace

BOOL WINAPI DllMain(HINSTANCE hinst, DWORD reason, LPVOID /*reserved*/) {
    if (reason == DLL_PROCESS_ATTACH) {
        g_hInstance = hinst;
        DisableThreadLibraryCalls(hinst);
    }
    return TRUE;
}

STDAPI DllCanUnloadNow() {
    return (g_cDllRef == 0) ? S_OK : S_FALSE;
}

STDAPI DllGetClassObject(REFCLSID rclsid, REFIID riid, void** ppv) {
    if (!ppv) {
        return E_POINTER;
    }
    *ppv = nullptr;
    if (rclsid != CLSID_BioUnlockProvider) {
        return CLASS_E_CLASSNOTAVAILABLE;
    }
    auto* factory = new (std::nothrow) CClassFactory();
    if (!factory) {
        return E_OUTOFMEMORY;
    }
    HRESULT hr = factory->QueryInterface(riid, ppv);
    factory->Release();
    return hr;
}
