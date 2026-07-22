import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/ui/theme.dart';

void main() {
  group('buildAppTheme', () {
    test('uses the shared palette and 16px body floor', () {
      final theme = buildAppTheme();

      expect(theme.colorScheme.brightness, Brightness.dark);
      expect(theme.colorScheme.primary, const Color(0xFFB8862E));
      expect(theme.colorScheme.onPrimary, const Color(0xFF211D1B));
      expect(theme.textTheme.bodyLarge!.fontSize, AppTextSize.body);
      expect(theme.textTheme.bodyMedium!.fontSize, AppTextSize.body);
    });

    test('registers AppStatusColors', () {
      final theme = buildAppTheme();
      expect(theme.extension<AppStatusColors>(), AppStatusColors.dark);
    });
  });

  group('AppStatusColors', () {
    const colors = AppStatusColors.dark;

    test('copyWith overrides only the given fields', () {
      final overridden = colors.copyWith(success: Colors.red);
      expect(overridden.success, Colors.red);
      expect(overridden.warning, colors.warning);
    });

    test('copyWith with no args returns equivalent values', () {
      final same = colors.copyWith();
      expect(same.success, colors.success);
      expect(same.warning, colors.warning);
    });

    test('lerp at t=0 returns this', () {
      const other = AppStatusColors(success: Colors.red, warning: Colors.blue);
      final result = colors.lerp(other, 0);
      expect(result.success, colors.success);
      expect(result.warning, colors.warning);
    });

    test('lerp at t=1 matches Color.lerp at t=1', () {
      const other = AppStatusColors(success: Colors.red, warning: Colors.blue);
      final result = colors.lerp(other, 1);
      expect(result.success, Color.lerp(colors.success, other.success, 1));
      expect(result.warning, Color.lerp(colors.warning, other.warning, 1));
    });

    test('lerp with a non-AppStatusColors other returns this unchanged', () {
      final result = colors.lerp(null, 0.5);
      expect(result, same(colors));
    });
  });
}
