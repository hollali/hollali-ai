from __future__ import annotations

from unittest.mock import patch, MagicMock

import system_control


class TestSystemControl:
    @patch("system_control.subprocess.run")
    def test_set_volume_clamps_above_100(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        result = system_control.set_volume(150)
        assert result is True
        call_args = mock_run.call_args[0][0]
        assert call_args[-1] == "100%"

    @patch("system_control.subprocess.run")
    def test_set_volume_clamps_below_0(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        result = system_control.set_volume(-10)
        assert result is True
        call_args = mock_run.call_args[0][0]
        assert call_args[-1] == "0%"

    @patch("system_control.subprocess.run")
    def test_set_volume_passes_through_mid_range(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        system_control.set_volume(50)
        call_args = mock_run.call_args[0][0]
        assert call_args[-1] == "50%"

    @patch("system_control.Path")
    def test_set_brightness_clamps_above_100(self, mock_path):
        mock_path.return_value.exists.return_value = True
        mock_dir = MagicMock()
        mock_dir.__truediv__.return_value = mock_dir
        mock_dir.read_text.return_value = "100"
        mock_path.return_value.iterdir.return_value = [mock_dir]
        result = system_control.set_brightness(200)
        assert result is True
        mock_dir.write_text.assert_called_with("100")

    @patch("system_control.Path")
    def test_set_brightness_clamps_below_0(self, mock_path):
        mock_path.return_value.exists.return_value = True
        mock_dir = MagicMock()
        mock_dir.__truediv__.return_value = mock_dir
        mock_dir.read_text.return_value = "100"
        mock_path.return_value.iterdir.return_value = [mock_dir]
        result = system_control.set_brightness(-5)
        assert result is True
        args = mock_dir.write_text.call_args[0][0]
        assert int(args) >= 1

    @patch("system_control.set_volume")
    def test_handle_system_command_volume_parsing(self, mock_set_volume):
        result = system_control.handle_system_command("set volume to 75 percent")
        assert "75" in result
        mock_set_volume.assert_called_with(75)

    @patch("system_control.set_volume")
    def test_handle_system_command_volume_max(self, mock_set_volume):
        result = system_control.handle_system_command("max volume")
        assert "maximum" in result
        mock_set_volume.assert_called_with(100)

    @patch("system_control.set_volume")
    def test_handle_system_command_volume_mute(self, mock_set_volume):
        result = system_control.handle_system_command("mute volume")
        assert "muted" in result
        mock_set_volume.assert_called_with(0)
