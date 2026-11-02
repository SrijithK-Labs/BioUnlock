import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../config.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/brand_mark.dart';
import '../widgets/glass_card.dart';

/// First-run screen: point the app at a self-hosted BioUnlock server.
class SetupScreen extends StatefulWidget {
  const SetupScreen({super.key});

  @override
  State<SetupScreen> createState() => _SetupScreenState();
}

class _SetupScreenState extends State<SetupScreen> {
  late final TextEditingController _controller = TextEditingController(
    text: AppConfig.defaultServerUrl,
  );
  final TextEditingController _tokenController = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    _tokenController.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final state = context.read<AppState>();
    final ok = await state.configureServer(
      _controller.text,
      token: _tokenController.text,
    );
    if (!mounted) return;
    if (ok) {
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Server connected.')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final scheme = context.scheme;

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(24, 32, 24, 32),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 460),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Center(child: BrandMark(size: 84)),
                  const SizedBox(height: 24),
                  Text(
                    'BioUnlock setup',
                    textAlign: TextAlign.center,
                    style: context.texts.labelLarge?.copyWith(
                      color: scheme.onSurfaceVariant,
                      letterSpacing: 1.5,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'Connect to your server',
                    textAlign: TextAlign.center,
                    style: context.texts.headlineSmall,
                  ),
                  const SizedBox(height: 10),
                  Text(
                    'BioUnlock is self-hosted. Enter your server address â€” a LAN '
                    'URL like http://192.168.1.10:8000 or an https:// tunnel.',
                    textAlign: TextAlign.center,
                    style: context.texts.bodyMedium?.copyWith(
                      color: scheme.onSurfaceVariant,
                      height: 1.45,
                    ),
                  ),
                  const SizedBox(height: 24),
                  GlassCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        TextField(
                          controller: _controller,
                          keyboardType: TextInputType.url,
                          autocorrect: false,
                          decoration: const InputDecoration(
                            labelText: 'Server URL',
                            hintText: 'http://192.168.1.10:8000',
                          ),
                        ),
                        const SizedBox(height: 16),
                        TextField(
                          controller: _tokenController,
                          autocorrect: false,
                          obscureText: true,
                          decoration: const InputDecoration(
                            labelText: 'API token',
                            helperText: 'Set as BIO_API_TOKEN on your server',
                          ),
                        ),
                        if (state.error != null) ...[
                          const SizedBox(height: 12),
                          Text(
                            state.error!,
                            style: context.texts.bodySmall?.copyWith(
                              color: scheme.error,
                            ),
                          ),
                        ],
                        const SizedBox(height: 20),
                        FilledButton.icon(
                          onPressed: state.busy ? null : _save,
                          icon: state.busy
                              ? const SizedBox(
                                  height: 18,
                                  width: 18,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                  ),
                                )
                              : const Icon(Icons.login_rounded),
                          label: const Text('Connect'),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
