function DynoLoggerAppM()
    % --- Configuration & Setup ---
    VERSION = "2.0.1";
    NM_TO_FTLBS = 0.7375621493;
    TORQUE_CONVERSION = -20 * NM_TO_FTLBS;
    ENGINE_FACTOR = 60 / 20; % 20 pulses per rev
    SCAN_RATE = 25000;
    SCANS_PER_READ = 100;

    % App State Variables (Stored in a struct to share across callbacks)
    state.LoggingState = 0; % 0: Stopped, 1: Logging, 2: Finalizing
    state.LJHandle = 0;
    state.DataDir = "";
    state.CurrentFileID = -1;
    state.CurrentFilename = "";
    state.SampleCount = 0;
    state.LastEngineCount = 0;
    state.LastVisualUpdate = tic;
    state.VisualTickSum = 0;
    state.StreamTimer = [];
    state.NumChannels = 0;
    state.ActualScanRate = 0;

    % Setup Data Directory
    if isdeployed
        state.DataDir = fullfile(ctfroot, 'data');
    else
        state.DataDir = fullfile(pwd, 'data');
    end
    if ~exist(state.DataDir, 'dir')
        mkdir(state.DataDir);
    end

    % --- UI Layout ---
    % Create the main window
    window = uifigure('Name', "Labjack-Dyno Interface v" + VERSION, ...
                      'Position', [100, 100, 500, 470], ...
                      'Color', [0.15, 0.15, 0.15]); % Dark theme

    % Title Label
    uilabel(window, ...
            'Text', "Cobra Dyno Logger", ...
            'FontName', 'Helvetica', ...
            'FontSize', 24, ...
            'FontWeight', 'bold', ...
            'FontColor', [1, 1, 1], ...
            'HorizontalAlignment', 'center', ...
            'Position', [50, 380, 400, 40]);

    % Start Button
    button_start = uibutton(window, ...
                            'Text', "START LOGGING", ...
                            'FontName', 'Helvetica', ...
                            'FontSize', 16, ...
                            'BackgroundColor', [0.12, 0.45, 0.74], ...
                            'FontColor', [1, 1, 1], ...
                            'Position', [125, 300, 250, 45], ...
                            'ButtonPushedFcn', @(~,~) start_log());

    % Stop Button
    button_stop = uibutton(window, ...
                           'Text', "STOP", ...
                           'FontName', 'Helvetica', ...
                           'FontSize', 16, ...
                           'BackgroundColor', [0.85, 0.33, 0.1], ...
                           'FontColor', [1, 1, 1], ...
                           'Position', [125, 230, 250, 45], ...
                           'ButtonPushedFcn', @(~,~) stop_log());

    % Info Label
    info_label = uilabel(window, ...
                         'Text', "Ready to Record", ...
                         'FontName', 'Helvetica', ...
                         'FontSize', 18, ...
                         'FontColor', [0.7, 0.7, 0.7], ...
                         'HorizontalAlignment', 'center', ...
                         'Position', [50, 80, 400, 100]);

    % Handle window close event cleanly
    window.CloseRequestFcn = @(~,~) close_app();

    % --- Core Functions ---

    function handle = openLabJack()
        try
            NET.addAssembly('LabJack.LJM');
            [err, handle] = LabJack.LJM.OpenS('T7', 'ANY', 'ANY', 0);
            if err ~= 0, error('Failed to open T7'); end
            
            aNames = {'AIN0_RANGE', 'AIN0_RESOLUTION_INDEX', 'AIN0_NEGATIVE_CH', ...
                      'AIN0_SETTLING_US', 'AIN2_RANGE', 'AIN2_RESOLUTION_INDEX', ...
                      'AIN2_NEGATIVE_CH', 'AIN2_SETTLING_US', 'STREAM_SETTLING_US', ...
                      'DIO0_EF_ENABLE', 'DIO0_EF_INDEX'};
            aValues = [10, 0, 1, 0, 10, 0, 3, 0, 0, 0, 8];
            LabJack.LJM.eWriteNames(handle, length(aNames), aNames, aValues, 0);
            LabJack.LJM.eWriteName(handle, 'DIO0_EF_ENABLE', 1);
        catch ME
            logMessage("ERROR", "LabJack Connection Error: " + ME.message);
            handle = 0;
        end
    end

    function full_path = makeNewFile()
        i = 1;
        while exist(fullfile(state.DataDir, sprintf('LJdata%d.csv', i)), 'file')
            i = i + 1;
        end
        state.CurrentFilename = fullfile(state.DataDir, sprintf('LJdata%d.csv', i));
        full_path = state.CurrentFilename;
        
        state.CurrentFileID = fopen(full_path, 'w');
        fprintf(state.CurrentFileID, 'Time (s),Torque (Ft-Lbs),Shaft Speed (RPM),Engine Speed (RPM)\n');
    end

    function start_log()
        if state.LoggingState ~= 0, return; end
        
        info_label.Text = "Initializing...";
        info_label.FontColor = [0.2, 0.6, 1];
        drawnow;
        
        makeNewFile();
        state.LJHandle = openLabJack();
        
        if state.LJHandle == 0
            info_label.Text = "No LabJack Found";
            info_label.FontColor = [1, 0.3, 0.3];
            return;
        end
        
        state.LoggingState = 1;
        
        aScanListNames = {'AIN0', 'AIN2', 'DIO0_EF_READ_A', 'STREAM_DATA_CAPTURE_16'};
        state.NumChannels = length(aScanListNames);
        
        aScanList = zeros(1, state.NumChannels, 'int32');
        [~, aScanList] = LabJack.LJM.namesToAddresses(state.NumChannels, aScanListNames, aScanList, zeros(1, state.NumChannels, 'int32'));
        
        LabJack.LJM.eReadName(state.LJHandle, 'DIO0_EF_READ_A_AND_RESET', 0);
        
        [err, actualRate] = LabJack.LJM.eStreamStart(state.LJHandle, SCANS_PER_READ, state.NumChannels, aScanList, SCAN_RATE);
        if err ~= 0, error('Stream failed to start'); end
        state.ActualScanRate = actualRate;
        
        state.SampleCount = 0;
        state.LastEngineCount = 0;
        state.VisualTickSum = 0;
        state.LastVisualUpdate = tic;
        
        % Start Background Timer for Data Ingestion
        state.StreamTimer = timer('ExecutionMode', 'fixedRate', ...
                                  'Period', 0.01, ...
                                  'TimerFcn', @(~,~) stream_callback());
        start(state.StreamTimer);
    end

    function stream_callback()
        if state.LoggingState == 0, return; end
        
        try
            [err, aData, ~, ~] = LabJack.LJM.eStreamRead(state.LJHandle, SCANS_PER_READ, ...
                                     zeros(1, SCANS_PER_READ * state.NumChannels), 0, 0);
            
            if err == 0
                matData = reshape(double(aData), state.NumChannels, [])';
                numScans = size(matData, 1);
                
                inverseScanRate = 1.0 / state.ActualScanRate;
                preciseTimes = ((0:numScans-1)' + state.SampleCount) * inverseScanRate;
                
                torques = matData(:, 1) * TORQUE_CONVERSION;
                shaftRpms = max(0, matData(:, 2) * 1200);
                
                col2 = int64(matData(:, 3));
                col3 = int64(matData(:, 4));
                rawEngineCounts = col2 + bitshift(col3, 16);
                
                countsWithBridge = [state.LastEngineCount; rawEngineCounts];
                deltaTicks = diff(countsWithBridge);
                engineRpms = deltaTicks * (state.ActualScanRate * ENGINE_FACTOR);
                
                processedBatch = [preciseTimes, torques, shaftRpms, engineRpms];
                fprintf(state.CurrentFileID, '%.4f,%.4f,%.4f,%.4f\n', processedBatch');
                
                state.SampleCount = state.SampleCount + numScans;
                state.LastEngineCount = rawEngineCounts(end);
                state.VisualTickSum = state.VisualTickSum + sum(deltaTicks);
                
                elapsed = toc(state.LastVisualUpdate);
                if elapsed > 0.1
                    engineRpmAvg = (state.VisualTickSum / elapsed) * ENGINE_FACTOR;
                    
                    info_label.Text = sprintf(...
                        "Torque: %.2f Ft-Lbs\nShaft: %.2f RPM\nEngine: %.2f RPM", ...
                        torques(end), shaftRpms(end), engineRpmAvg);
                    
                    state.LastVisualUpdate = tic;
                    state.VisualTickSum = 0;
                end
            end
        catch ME
            logMessage("ERROR", "Stream Exception: " + ME.message);
        end
        
        if state.LoggingState == 2
            stop_hardware();
        end
    end

    function stop_log()
        if state.LoggingState == 1
            state.LoggingState = 2;
            info_label.Text = "Finalizing data...";
            info_label.FontColor = [1, 0.7, 0.1];
        end
    end

    function stop_hardware()
        if state.LJHandle ~= 0
            stop(state.StreamTimer);
            pause(0.2);
            
            LabJack.LJM.eStreamStop(state.LJHandle);
            LabJack.LJM.Close(state.LJHandle);
            fclose(state.CurrentFileID);
            
            state.LJHandle = 0;
            state.LoggingState = 0;
            info_label.Text = sprintf("Logging Stopped\nFile saved to:\n%s", state.CurrentFilename);
            info_label.FontColor = [0.3, 0.9, 0.4];
        end
    end

    function close_app()
        state.LoggingState = 2;
        stop_hardware();
        if ~isempty(state.StreamTimer)
            delete(state.StreamTimer);
        end
        delete(window);
    end

    function logMessage(level, msg)
        fileID = fopen('app.log', 'a');
        fprintf(fileID, '%s:[%s]:%s\n', datestr(now, 'yyyy-mm-dd HH:MM:SS'), level, msg);
        fclose(fileID);
    end
end