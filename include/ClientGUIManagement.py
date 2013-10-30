import HydrusConstants as HC
import HydrusAudioHandling
import HydrusDownloading
import HydrusExceptions
import HydrusFileHandling
import HydrusImageHandling
import ClientConstants as CC
import ClientConstantsMessages
import ClientGUICommon
import ClientGUIDialogs
import ClientGUIMedia
import ClientGUIMixins
import ClientParsers
import json
import os
import threading
import time
import traceback
import urllib
import urlparse
import wx
import wx.lib.scrolledpanel
import zipfile

CAPTCHA_FETCH_EVENT_TYPE = wx.NewEventType()
CAPTCHA_FETCH_EVENT = wx.PyEventBinder( CAPTCHA_FETCH_EVENT_TYPE )

ID_TIMER_CAPTCHA = wx.NewId()
ID_TIMER_DUMP = wx.NewId()
ID_TIMER_PROCESS_IMPORT_QUEUE = wx.NewId()
ID_TIMER_PROCESS_OUTER_QUEUE = wx.NewId()

# Sizer Flags

FLAGS_NONE = wx.SizerFlags( 0 )

FLAGS_SMALL_INDENT = wx.SizerFlags( 0 ).Border( wx.ALL, 2 )

FLAGS_EXPAND_PERPENDICULAR = wx.SizerFlags( 0 ).Border( wx.ALL, 2 ).Expand()
FLAGS_EXPAND_BOTH_WAYS = wx.SizerFlags( 2 ).Border( wx.ALL, 2 ).Expand()
FLAGS_EXPAND_DEPTH_ONLY = wx.SizerFlags( 2 ).Border( wx.ALL, 2 ).Align( wx.ALIGN_CENTER_VERTICAL )

FLAGS_EXPAND_SIZER_PERPENDICULAR = wx.SizerFlags( 0 ).Expand()
FLAGS_EXPAND_SIZER_BOTH_WAYS = wx.SizerFlags( 2 ).Expand()
FLAGS_EXPAND_SIZER_DEPTH_ONLY = wx.SizerFlags( 2 ).Align( wx.ALIGN_CENTER_VERTICAL )

FLAGS_BUTTON_SIZERS = wx.SizerFlags( 0 ).Align( wx.ALIGN_RIGHT )
FLAGS_LONE_BUTTON = wx.SizerFlags( 0 ).Border( wx.ALL, 2 ).Align( wx.ALIGN_RIGHT )

FLAGS_MIXED = wx.SizerFlags( 0 ).Border( wx.ALL, 2 ).Align( wx.ALIGN_CENTER_VERTICAL )

class CaptchaControl( wx.Panel ):
    
    def __init__( self, parent, type, default ):
        
        wx.Panel.__init__( self, parent )
        
        self._captcha_key = default
        
        self._captcha_challenge = None
        self._captcha_runs_out = 0
        self._bitmap = wx.EmptyBitmap( 0, 0, 24 )
        
        self._timer = wx.Timer( self, ID_TIMER_CAPTCHA )
        self.Bind( wx.EVT_TIMER, self.EventTimer, id = ID_TIMER_CAPTCHA )
        
        self._captcha_box_panel = ClientGUICommon.StaticBox( self, 'recaptcha' )
        
        self._captcha_panel = ClientGUICommon.BufferedWindow( self._captcha_box_panel, size = ( 300, 57 ) )
        
        self._refresh_button = wx.Button( self._captcha_box_panel, label = '' )
        self._refresh_button.Bind( wx.EVT_BUTTON, self.EventRefreshCaptcha )
        self._refresh_button.Disable()
        
        self._captcha_time_left = wx.StaticText( self._captcha_box_panel )
        
        self._captcha_entry = wx.TextCtrl( self._captcha_box_panel, style = wx.TE_PROCESS_ENTER )
        self._captcha_entry.Bind( wx.EVT_KEY_DOWN, self.EventKeyDown )
        
        self._ready_button = wx.Button( self._captcha_box_panel, label = '' )
        self._ready_button.Bind( wx.EVT_BUTTON, self.EventReady )
        
        sub_vbox = wx.BoxSizer( wx.VERTICAL )
        
        sub_vbox.AddF( self._refresh_button, FLAGS_EXPAND_BOTH_WAYS )
        sub_vbox.AddF( self._captcha_time_left, FLAGS_SMALL_INDENT )
        
        hbox = wx.BoxSizer( wx.HORIZONTAL )
        
        hbox.AddF( self._captcha_panel, FLAGS_NONE )
        hbox.AddF( sub_vbox, FLAGS_EXPAND_SIZER_BOTH_WAYS )
        
        hbox2 = wx.BoxSizer( wx.HORIZONTAL )
        
        hbox2.AddF( self._captcha_entry, FLAGS_EXPAND_BOTH_WAYS )
        hbox2.AddF( self._ready_button, FLAGS_MIXED )
        
        self._captcha_box_panel.AddF( hbox, FLAGS_EXPAND_SIZER_PERPENDICULAR )
        self._captcha_box_panel.AddF( hbox2, FLAGS_EXPAND_SIZER_PERPENDICULAR )
        
        vbox = wx.BoxSizer( wx.VERTICAL )
        
        vbox.AddF( self._captcha_box_panel, FLAGS_EXPAND_BOTH_WAYS )
        
        self.SetSizer( vbox )
        
        self.Disable()
        
    
    def _DrawEntry( self, entry = None ):
        
        if entry is None:
            
            self._captcha_entry.SetValue( '' )
            self._captcha_entry.Disable()
            
        else: self._captcha_entry.SetValue( entry )
        
    
    def _DrawMain( self ):
        
        dc = self._captcha_panel.GetDC()
        
        if self._captcha_challenge is None:
            
            dc.SetBackground( wx.Brush( wx.WHITE ) )
            
            dc.Clear()
            
            self._refresh_button.SetLabel( '' )
            self._refresh_button.Disable()
            
            self._captcha_time_left.SetLabel( '' )
            
        elif self._captcha_challenge == '':
            
            dc.SetBackground( wx.Brush( wx.WHITE ) )
            
            dc.Clear()
            
            event = wx.NotifyEvent( CAPTCHA_FETCH_EVENT_TYPE )
            
            self.ProcessEvent( event )
            
            if event.IsAllowed():
                
                self._refresh_button.SetLabel( 'get captcha' )
                self._refresh_button.Enable()
                
            else:
                
                self._refresh_button.SetLabel( 'not yet' )
                self._refresh_button.Disable()
                
            
            self._captcha_time_left.SetLabel( '' )
            
        else:
            
            hydrus_bmp = self._bitmap.CreateWxBmp()
            
            dc.DrawBitmap( hydrus_bmp, 0, 0 )
            
            hydrus_bmp.Destroy()
            
            self._refresh_button.SetLabel( 'get new captcha' )
            self._refresh_button.Enable()
            
            self._captcha_time_left.SetLabel( HC.ConvertTimestampToPrettyExpires( self._captcha_runs_out ) )
            
        
        del dc
        
    
    def _DrawReady( self, ready = None ):
        
        if ready is None:
            
            self._ready_button.SetLabel( '' )
            self._ready_button.Disable()
            
        else:
            
            if ready:
                
                self._captcha_entry.Disable()
                self._ready_button.SetLabel( 'edit' )
                
            else:
                
                self._captcha_entry.Enable()
                self._ready_button.SetLabel( 'ready' )
                
            
            self._ready_button.Enable()
            
        
    
    def Disable( self ):
        
        self._captcha_challenge = None
        self._captcha_runs_out = 0
        self._bitmap = wx.EmptyBitmap( 0, 0, 24 )
        
        self._DrawMain()
        self._DrawEntry()
        self._DrawReady()
        
        self._timer.Stop()
        
    
    def Enable( self ):
        
        self._captcha_challenge = ''
        self._captcha_runs_out = 0
        self._bitmap = wx.EmptyBitmap( 0, 0, 24 )
        
        self._DrawMain()
        self._DrawEntry()
        self._DrawReady()
        
        self._timer.Start( 1000, wx.TIMER_CONTINUOUS )
        
    
    def EnableWithValues( self, challenge, bitmap, captcha_runs_out, entry, ready ):
        
        if HC.GetNow() > captcha_runs_out: self.Enable()
        else:
            
            self._captcha_challenge = challenge
            self._captcha_runs_out = captcha_runs_out
            self._bitmap = bitmap
            
            self._DrawMain()
            self._DrawEntry( entry )
            self._DrawReady( ready )
            
            self._timer.Start( 1000, wx.TIMER_CONTINUOUS )
            
        
    
    def EventKeyDown( self, event ):
        
        if event.KeyCode in ( wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER ): self.EventReady( None )
        else: event.Skip()
        
    
    def EventReady( self, event ): self._DrawReady( not self._ready_button.GetLabel() == 'edit' )
    
    def EventRefreshCaptcha( self, event ):
        
        try:
            
            connection = HC.get_connection( scheme = 'http', host = 'www.google.com', port = 80 )
            
            javascript_string = connection.request( 'GET', '/recaptcha/api/challenge?k=' + self._captcha_key )
            
            ( trash, rest ) = javascript_string.split( 'challenge : \'', 1 )
            
            ( self._captcha_challenge, trash ) = rest.split( '\'', 1 )
            
            jpeg = connection.request( 'GET', '/recaptcha/api/image?c=' + self._captcha_challenge )
            
            temp_path = HC.GetTempPath()
            
            with open( temp_path, 'wb' ) as f: f.write( jpeg )
            
            self._bitmap = HydrusImageHandling.GenerateHydrusBitmap( temp_path )
            
            self._captcha_runs_out = HC.GetNow() + 5 * 60 - 15
            
            self._DrawMain()
            self._DrawEntry( '' )
            self._DrawReady( False )
            
            self._timer.Start( 1000, wx.TIMER_CONTINUOUS )
            
        except:
            
            wx.MessageBox( traceback.format_exc() )
            
        
    
    def EventTimer( self, event ):
        
        if HC.GetNow() > self._captcha_runs_out: self.Enable()
        else: self._DrawMain()
        
    
    # change this to hold (current challenge, bmp, timestamp it runs out, value, whethere ready to post)
    def GetValues( self ): return ( self._captcha_challenge, self._bitmap, self._captcha_runs_out, self._captcha_entry.GetValue(), self._ready_button.GetLabel() == 'edit' )
    
class Comment( wx.Panel ):
    
    def __init__( self, parent ):
        
        wx.Panel.__init__( self, parent )
        
        self._initial_comment = ''
        
        self._comment_panel = ClientGUICommon.StaticBox( self, 'comment' )
        
        self._comment = wx.TextCtrl( self._comment_panel, value = '', style = wx.TE_MULTILINE | wx.TE_READONLY, size = ( -1, 120 ) )
        
        self._comment_append = wx.TextCtrl( self._comment_panel, value = '', style = wx.TE_MULTILINE | wx.TE_PROCESS_ENTER, size = ( -1, 120 ) )
        self._comment_append.Bind( wx.EVT_KEY_UP, self.EventKeyDown )
        
        self._comment_panel.AddF( self._comment, FLAGS_EXPAND_PERPENDICULAR )
        self._comment_panel.AddF( self._comment_append, FLAGS_EXPAND_PERPENDICULAR )
        
        vbox = wx.BoxSizer( wx.VERTICAL )
        
        vbox.AddF( self._comment_panel, FLAGS_EXPAND_BOTH_WAYS )
        
        self.SetSizer( vbox )
        
    
    def _SetComment( self ):
        
        append = self._comment_append.GetValue()
        
        if self._initial_comment != '' and append != '': comment = self._initial_comment + os.linesep + os.linesep + append
        else: comment = self._initial_comment + append
        
        self._comment.SetValue( comment )
        
    
    def Disable( self ):
        
        self._initial_comment = ''
        
        self._comment_append.SetValue( '' )
        self._comment_append.Disable()
        
        self._SetComment()
        
    
    def EnableWithValues( self, initial, append ):
        
        self._initial_comment = initial
        
        self._comment_append.SetValue( append )
        self._comment_append.Enable()
        
        self._SetComment()
        
    
    def GetValues( self ): return ( self._initial_comment, self._comment_append.GetValue() )
    
    def EventKeyDown( self, event ):
        
        self._SetComment()
        
        event.Skip()
        
    
class ManagementPanel( wx.lib.scrolledpanel.ScrolledPanel ):
    
    def __init__( self, parent, page, page_key, file_service_identifier = HC.LOCAL_FILE_SERVICE_IDENTIFIER ):
        
        wx.lib.scrolledpanel.ScrolledPanel.__init__( self, parent, style = wx.BORDER_NONE | wx.VSCROLL )
        
        self.SetupScrolling()
        
        #self.SetBackgroundColour( wx.SystemSettings.GetColour( wx.SYS_COLOUR_BTNFACE ) )
        self.SetBackgroundColour( wx.WHITE )
        
        self._page = page
        self._page_key = page_key
        self._file_service_identifier = file_service_identifier
        self._tag_service_identifier = HC.COMBINED_TAG_SERVICE_IDENTIFIER
        
        self._paused = False
        
        HC.pubsub.sub( self, 'SetSearchFocus', 'set_search_focus' )
        HC.pubsub.sub( self, 'Pause', 'pause' )
        HC.pubsub.sub( self, 'Unpause', 'unpause' )
        
    
    def _MakeCollect( self, sizer ):
        
        self._collect_by = ClientGUICommon.CheckboxCollect( self, self._page_key )
        
        sizer.AddF( self._collect_by, FLAGS_EXPAND_PERPENDICULAR )
        
    
    def _MakeCurrentSelectionTagsBox( self, sizer ):
        
        tags_box = ClientGUICommon.TagsBoxCPPWithSorter( self, self._page_key )
        
        sizer.AddF( tags_box, FLAGS_EXPAND_BOTH_WAYS )
        
    
    def _MakeSort( self, sizer ):
        
        self._sort_by = ClientGUICommon.ChoiceSort( self, self._page_key )
        
        sizer.AddF( self._sort_by, FLAGS_EXPAND_PERPENDICULAR )
        
    
    def Pause( self, page_key ):
        
        if page_key == self._page_key: self._paused = True
        
    
    def SetSearchFocus( self, page_key ): pass
    
    def TryToClose( self ): pass
    
    def Unpause( self, page_key ):
        
        if page_key == self._page_key: self._paused = False
        
    
class ManagementPanelDumper( ManagementPanel ):
    
    def __init__( self, parent, page, page_key, imageboard, media_results ):
        
        ManagementPanel.__init__( self, parent, page, page_key )
        
        ( self._4chan_token, pin, timeout ) = HC.app.Read( '4chan_pass' )
        
        self._have_4chan_pass = timeout > HC.GetNow()
        
        self._imageboard = imageboard
        
        self._current_hash = None
        
        self._dumping = False
        self._actually_dumping = False
        self._num_dumped = 0
        self._next_dump_index = 0
        self._next_dump_time = 0
        
        self._file_post_name = 'upfile'
        
        self._timer = wx.Timer( self, ID_TIMER_DUMP )
        self.Bind( wx.EVT_TIMER, self.EventTimer, id = ID_TIMER_DUMP )
        
        ( post_url, self._flood_time, self._form_fields, self._restrictions ) = self._imageboard.GetBoardInfo()
        
        o = urlparse.urlparse( post_url )
        
        self._post_scheme = o.scheme
        self._post_host = o.hostname
        self._post_port = o.port
        self._post_request = o.path
        
        # progress
        
        self._processing_panel = ClientGUICommon.StaticBox( self, 'processing' )
        
        self._progress_info = wx.StaticText( self._processing_panel )
        
        self._progress_gauge = ClientGUICommon.Gauge( self._processing_panel )
        self._progress_gauge.SetRange( len( media_results ) )
        
        self._start_button = wx.Button( self._processing_panel, label = 'start' )
        self._start_button.Bind( wx.EVT_BUTTON, self.EventStartButton )
        
        self._processing_panel.AddF( self._progress_info, FLAGS_EXPAND_PERPENDICULAR )
        self._processing_panel.AddF( self._progress_gauge, FLAGS_EXPAND_PERPENDICULAR )
        self._processing_panel.AddF( self._start_button, FLAGS_EXPAND_PERPENDICULAR )
        
        # thread options
        
        self._thread_panel = ClientGUICommon.StaticBox( self, 'thread options' )
        
        self._thread_fields = {}
        
        gridbox = wx.FlexGridSizer( 0, 2 )
        
        gridbox.AddGrowableCol( 1, 1 )
        
        for ( name, type, default, editable ) in self._form_fields:
            
            if type in ( CC.FIELD_TEXT, CC.FIELD_THREAD_ID ): field = wx.TextCtrl( self._thread_panel, value = default )
            elif type == CC.FIELD_PASSWORD: field = wx.TextCtrl( self._thread_panel, value = default, style = wx.TE_PASSWORD )
            else: continue
            
            self._thread_fields[ name ] = ( type, field )
            
            if editable:
                
                gridbox.AddF( wx.StaticText( self._thread_panel, label = name + ':' ), FLAGS_MIXED )
                gridbox.AddF( field, FLAGS_EXPAND_BOTH_WAYS )
                
            else: field.Hide()
            
        
        self._thread_panel.AddF( gridbox, FLAGS_EXPAND_SIZER_PERPENDICULAR )
        
        # post options
        
        self._post_panel = ClientGUICommon.StaticBox( self, 'post options' )
        
        self._post_fields = {}
        
        postbox = wx.BoxSizer( wx.VERTICAL )
        
        self._post_info = wx.StaticText( self._post_panel, label = 'no file selected', style = wx.ALIGN_CENTER | wx.ST_NO_AUTORESIZE )
        
        for ( name, type, default, editable ) in self._form_fields:
            
            if type == CC.FIELD_VERIFICATION_RECAPTCHA:
                
                if self._have_4chan_pass: continue
                
                field = CaptchaControl( self._post_panel, type, default )
                field.Bind( CAPTCHA_FETCH_EVENT, self.EventCaptchaRefresh )
                
            elif type == CC.FIELD_COMMENT: field = Comment( self._post_panel )
            else: continue
            
            self._post_fields[ name ] = ( type, field, default )
            
            postbox.AddF( field, FLAGS_EXPAND_PERPENDICULAR )
            
        
        gridbox = wx.FlexGridSizer( 0, 2 )
        
        gridbox.AddGrowableCol( 1, 1 )
        
        for ( name, type, default, editable ) in self._form_fields:
            
            if type == CC.FIELD_CHECKBOX:
                
                field = wx.CheckBox( self._post_panel )
                
                field.SetValue( default == 'True' )
                
            else: continue
            
            self._post_fields[ name ] = ( type, field, default )
            
            gridbox.AddF( wx.StaticText( self._post_panel, label = name + ':' ), FLAGS_MIXED )
            gridbox.AddF( field, FLAGS_EXPAND_BOTH_WAYS )
            
        
        for ( name, type, default, editable ) in self._form_fields:
            
            if type == CC.FIELD_FILE: self._file_post_name = name
            
        
        self._post_panel.AddF( self._post_info, FLAGS_EXPAND_PERPENDICULAR )
        self._post_panel.AddF( postbox, FLAGS_EXPAND_SIZER_PERPENDICULAR )
        self._post_panel.AddF( gridbox, FLAGS_EXPAND_SIZER_PERPENDICULAR )
        
        # misc
        
        self._advanced_tag_options = ClientGUICommon.AdvancedTagOptions( self, 'include tags from', namespaces = [ 'creator', 'series', 'title', 'volume', 'chapter', 'page', 'character', 'person', 'all others' ] )
        
        # arrange stuff
        
        vbox = wx.BoxSizer( wx.VERTICAL )
        
        self._MakeSort( vbox )
        
        vbox.AddF( self._processing_panel, FLAGS_EXPAND_PERPENDICULAR )
        vbox.AddF( self._thread_panel, FLAGS_EXPAND_PERPENDICULAR )
        vbox.AddF( self._post_panel, FLAGS_EXPAND_PERPENDICULAR )
        vbox.AddF( self._advanced_tag_options, FLAGS_EXPAND_PERPENDICULAR )
        
        self._MakeCurrentSelectionTagsBox( vbox )
        
        self.SetSizer( vbox )
        
        HC.pubsub.sub( self, 'FocusChanged', 'focus_changed' )
        HC.pubsub.sub( self, 'SortedMediaPulse', 'sorted_media_pulse' )
        
        self._sorted_media_hashes = [ media_result.GetHash() for media_result in media_results ]
        
        self._hashes_to_media = { media_result.GetHash() : ClientGUIMixins.MediaSingleton( media_result ) for media_result in media_results }
        
        self._hashes_to_dump_info = {}
        
        for ( hash, media ) in self._hashes_to_media.items():
            
            dump_status_enum = CC.DUMPER_NOT_DUMPED
            
            dump_status_string = 'not yet dumped'
            
            post_field_info = []
            
            for ( name, ( type, field, default ) ) in self._post_fields.items():
                
                if type == CC.FIELD_COMMENT:
                    
                    post_field_info.append( ( name, type, ( self._GetInitialComment( media ), '' ) ) )
                    
                elif type == CC.FIELD_CHECKBOX: post_field_info.append( ( name, type, default == 'True' ) )
                elif type == CC.FIELD_VERIFICATION_RECAPTCHA: post_field_info.append( ( name, type, None ) )
                
            
            self._hashes_to_dump_info[ hash ] = ( dump_status_enum, dump_status_string, post_field_info )
            
        
        self.Bind( wx.EVT_MENU, self.EventMenu )
        
        self._timer.Start( 1000, wx.TIMER_CONTINUOUS )
        
    
    def _THREADDoDump( self, hash, post_field_info, headers, body ):
        
        try:
            
            connection = HC.get_connection( scheme = self._post_scheme, host = self._post_host, port = self._post_port )
            
            data = connection.request( 'POST', self._post_request, headers = headers, body = body )
            
            ( status, phrase ) = ClientParsers.Parse4chanPostScreen( data )
            
        except Exception as e: ( status, phrase ) = ( 'big error', HC.u( e ) )
        
        wx.CallAfter( self.CALLBACKDoneDump, hash, post_field_info, status, phrase )
        
    
    def _FreezeCurrentMediaPostInfo( self ):
        
        ( dump_status_enum, dump_status_string, post_field_info ) = self._hashes_to_dump_info[ self._current_hash ]
        
        post_field_info = []
        
        for ( name, ( type, field, default ) ) in self._post_fields.items():
            
            if type == CC.FIELD_COMMENT: post_field_info.append( ( name, type, field.GetValues() ) )
            elif type == CC.FIELD_CHECKBOX: post_field_info.append( ( name, type, field.GetValue() ) )
            elif type == CC.FIELD_VERIFICATION_RECAPTCHA: post_field_info.append( ( name, type, field.GetValues() ) )
            
        
        self._hashes_to_dump_info[ self._current_hash ] = ( dump_status_enum, dump_status_string, post_field_info )
        
    
    def _GetInitialComment( self, media ):
        
        hash = media.GetHash()
        
        try: index = self._sorted_media_hashes.index( hash )
        except: return 'media removed'
        
        num_files = len( self._sorted_media_hashes )
        
        if index == 0:
            
            total_size = sum( [ m.GetSize() for m in self._hashes_to_media.values() ] )
            
            initial = 'Hydrus Network Client is starting a dump of ' + HC.u( num_files ) + ' files, totalling ' + HC.ConvertIntToBytes( total_size ) + ':' + os.linesep + os.linesep
            
        else: initial = ''
        
        initial += HC.u( index + 1 ) + '/' + HC.u( num_files )
        
        advanced_tag_options = self._advanced_tag_options.GetInfo()
        
        for ( service_identifier, namespaces ) in advanced_tag_options.items():
            
            tags_manager = media.GetTagsManager()
            
            current = tags_manager.GetCurrent( service_identifier )
            pending = tags_manager.GetPending( service_identifier )
            
            tags = current.union( pending )
            
            tags_to_include = []
            
            for namespace in namespaces:
                
                if namespace == 'all others': tags_to_include.extend( [ tag for tag in tags if not True in ( tag.startswith( n ) for n in namespaces if n != 'all others' ) ] )
                else: tags_to_include.extend( [ tag for tag in tags if tag.startswith( namespace + ':' ) ] )
                
            
            initial += os.linesep + os.linesep + ', '.join( tags_to_include )
            
        
        return initial
        
    
    def _ShowCurrentMedia( self ):
        
        if self._current_hash is None:
            
            self._post_info.SetLabel( 'no file selected' )
            
            for ( name, ( type, field, default ) ) in self._post_fields.items():
                
                if type == CC.FIELD_CHECKBOX: field.SetValue( False )
                
                field.Disable()
                
            
        else:
            
            num_files = len( self._sorted_media_hashes )
            
            ( dump_status_enum, dump_status_string, post_field_info ) = self._hashes_to_dump_info[ self._current_hash ]
            
            index = self._sorted_media_hashes.index( self._current_hash )
            
            self._post_info.SetLabel( HC.u( index + 1 ) + '/' + HC.u( num_files ) + ': ' + dump_status_string )
            
            for ( name, type, value ) in post_field_info:
                
                ( type, field, default ) = self._post_fields[ name ]
                
                if type == CC.FIELD_COMMENT:
                    
                    ( initial, append ) = value
                    
                    field.EnableWithValues( initial, append )
                    
                elif type == CC.FIELD_CHECKBOX:
                    
                    field.SetValue( value )
                    field.Enable()
                    
                elif type == CC.FIELD_VERIFICATION_RECAPTCHA:
                    
                    if value is None: field.Enable()
                    else:
                        
                        ( challenge, bitmap, captcha_runs_out, entry, ready ) = value
                        
                        field.EnableWithValues( challenge, bitmap, captcha_runs_out, entry, ready )
                        
                    
                
            
            if dump_status_enum in ( CC.DUMPER_DUMPED_OK, CC.DUMPER_UNRECOVERABLE_ERROR ):
                
                for ( name, ( type, field, default ) ) in self._post_fields.items():
                    
                    if type == CC.FIELD_CHECKBOX: field.SetValue( False )
                    
                    field.Disable()
                    
                
            
        
    
    def _UpdatePendingInitialComments( self ):
        
        hashes_to_dump = self._sorted_media_hashes[ self._next_dump_index : ]
        
        for hash in hashes_to_dump:
            
            if hash == self._current_hash: self._FreezeCurrentMediaPostInfo()
            
            ( dump_status_enum, dump_status_string, post_field_info ) = self._hashes_to_dump_info[ hash ]
            
            new_post_field_info = []
            
            for ( name, type, value ) in post_field_info:
                
                if type == CC.FIELD_COMMENT:
                    
                    ( initial, append ) = value
                    
                    media = self._hashes_to_media[ hash ]
                    
                    initial = self._GetInitialComment( media )
                    
                    new_post_field_info.append( ( name, type, ( initial, append ) ) )
                    
                else: new_post_field_info.append( ( name, type, value ) )
                
            
            self._hashes_to_dump_info[ hash ] = ( dump_status_enum, dump_status_string, new_post_field_info )
            
            if hash == self._current_hash: self._ShowCurrentMedia()
            
        
    
    def CALLBACKDoneDump( self, hash, post_field_info, status, phrase ):
        
        self._actually_dumping = False
        
        if HC.options[ 'play_dumper_noises' ]:
            
            if status == 'success': HydrusAudioHandling.PlayNoise( 'success' )
            else: HydrusAudioHandling.PlayNoise( 'error' )
            
        
        if status == 'success':
            
            dump_status_enum = CC.DUMPER_DUMPED_OK
            dump_status_string = 'dumped ok'
            
            if hash == self._current_hash: HC.pubsub.pub( 'set_focus', self._page_key, None )
            
            self._next_dump_time = HC.GetNow() + self._flood_time
            
            self._num_dumped += 1
            
            self._progress_gauge.SetValue( self._num_dumped )
            
            self._next_dump_index += 1
            
        elif status == 'captcha':
            
            dump_status_enum = CC.DUMPER_RECOVERABLE_ERROR
            dump_status_string = 'captcha was incorrect'
            
            self._next_dump_time = HC.GetNow() + 10
            
            new_post_field_info = []
            
            for ( name, type, value ) in post_field_info:
                
                if type == CC.FIELD_VERIFICATION_RECAPTCHA: new_post_field_info.append( ( name, type, None ) )
                else: new_post_field_info.append( ( name, type, value ) )
                
                if hash == self._current_hash:
                    
                    ( type, field, default ) = self._post_fields[ name ]
                    
                    field.Enable()
                    
                
            
            post_field_info = new_post_field_info
            
        elif status == 'too quick':
            
            dump_status_enum = CC.DUMPER_RECOVERABLE_ERROR
            dump_status_string = ''
            
            self._progress_info.SetLabel( 'Flood limit hit, retrying.' )
            
            self._next_dump_time = HC.GetNow() + self._flood_time
            
        elif status == 'big error':
            
            dump_status_enum = CC.DUMPER_UNRECOVERABLE_ERROR
            dump_status_string = ''
            
            HC.pubsub.pub( 'message', HC.Message( HC.MESSAGE_TYPE_TEXT, phrase ) )
            
            self._progress_info.SetLabel( 'error: ' + phrase )
            
            self._start_button.Disable()
            
            self._timer.Stop()
            
        elif 'Thread specified does not exist' in phrase:
            
            dump_status_enum = CC.DUMPER_UNRECOVERABLE_ERROR
            dump_status_string = ''
            
            self._progress_info.SetLabel( 'thread specified does not exist!' )
            
            self._start_button.Disable()
            
            self._timer.Stop()
            
        else:
            
            dump_status_enum = CC.DUMPER_UNRECOVERABLE_ERROR
            dump_status_string = phrase
            
            if hash == self._current_hash: HC.pubsub.pub( 'set_focus', self._page_key, None )
            
            self._next_dump_time = HC.GetNow() + self._flood_time
            
            self._next_dump_index += 1
            
        
        self._hashes_to_dump_info[ hash ] = ( dump_status_enum, dump_status_string, post_field_info )
        
        HC.pubsub.pub( 'file_dumped', self._page_key, hash, dump_status_enum )
        
        if self._next_dump_index == len( self._sorted_media_hashes ):
            
            self._progress_info.SetLabel( 'done - ' + HC.u( self._num_dumped ) + ' dumped' )
            
            self._start_button.Disable()
            
            self._timer.Stop()
            
            self._dumping = False
            
        
    
    def EventCaptchaRefresh( self, event ):
        
        try:
            
            index = self._sorted_media_hashes.index( self._current_hash )
            
            if ( ( index + 1 ) - self._next_dump_index ) * ( self._flood_time + 10 ) > 5 * 60: event.Veto()
            
        except: event.Veto()
        
    
    def EventMenu( self, event ):
        
        action = CC.MENU_EVENT_ID_TO_ACTION_CACHE.GetAction( event.GetId() )
        
        if action is not None:
            
            ( command, data ) = action
            
            if command == 'advanced_tag_options_changed': self._UpdatePendingInitialComments()
            else: event.Skip()
            
        
    
    def EventStartButton( self, event ):
        
        if self._start_button.GetLabel() in ( 'start', 'continue' ):
            
            for ( name, ( type, field ) ) in self._thread_fields.items():
                
                if type == CC.FIELD_THREAD_ID:
                    
                    try: int( field.GetValue() )
                    except:
                        
                        # let's assume they put the url in
                        
                        value = field.GetValue()
                        
                        thread_id = value.split( '/' )[ -1 ]
                        
                        try: int( thread_id )
                        except:
                            
                            self._progress_info.SetLabel( 'set thread_id field first' )
                            
                            return
                            
                        
                        field.SetValue( thread_id )
                        
                    
                
            
            for ( type, field ) in self._thread_fields.values(): field.Disable()
            
            self._dumping = True
            self._start_button.SetLabel( 'pause' )
            
            if self._next_dump_time == 0: self._next_dump_time = HC.GetNow() + 5
            
            # disable thread fields here
            
        else:
            
            for ( type, field ) in self._thread_fields.values(): field.Enable()
            
            self._dumping = False
            
            if self._num_dumped == 0: self._start_button.SetLabel( 'start' )
            else: self._start_button.SetLabel( 'continue' )
            
        
    
    def EventTimer( self, event ):
        
        if self._paused: return
        
        if self._actually_dumping: return
        
        if self._dumping:
            
            time_left = self._next_dump_time - HC.GetNow()
            
            if time_left < 1:
                
                try:
                    
                    hash = self._sorted_media_hashes[ self._next_dump_index ]
                    
                    wait = False
                    
                    if hash == self._current_hash: self._FreezeCurrentMediaPostInfo()
                    
                    ( dump_status_enum, dump_status_string, post_field_info ) = self._hashes_to_dump_info[ hash ]
                    
                    for ( name, type, value ) in post_field_info:
                        
                        if type == CC.FIELD_VERIFICATION_RECAPTCHA:
                            
                            if value is None:
                                
                                wait = True
                                
                                break
                                
                            else:
                                
                                ( challenge, bitmap, captcha_runs_out, entry, ready ) = value
                                
                                if HC.GetNow() > captcha_runs_out or not ready:
                                    
                                    wait = True
                                    
                                    break
                                    
                                
                            
                        
                    
                    if wait: self._progress_info.SetLabel( 'waiting for captcha' )
                    else:
                        
                        self._progress_info.SetLabel( 'dumping' ) # 100% cpu time here - may or may not be desirable
                        
                        post_fields = []
                        
                        for ( name, ( type, field ) ) in self._thread_fields.items():
                            
                            post_fields.append( ( name, type, field.GetValue() ) )
                            
                        
                        for ( name, type, value ) in post_field_info:
                            
                            if type == CC.FIELD_VERIFICATION_RECAPTCHA:
                                
                                ( challenge, bitmap, captcha_runs_out, entry, ready ) = value
                                
                                post_fields.append( ( 'recaptcha_challenge_field', type, challenge ) )
                                post_fields.append( ( 'recaptcha_response_field', type, entry ) )
                                
                            elif type == CC.FIELD_COMMENT:
                                
                                ( initial, append ) = value
                                
                                comment = initial
                                
                                if len( append ) > 0: comment += os.linesep + os.linesep + append
                                
                                post_fields.append( ( name, type, comment ) )
                                
                            else: post_fields.append( ( name, type, value ) )
                            
                        
                        media = self._hashes_to_media[ hash ]
                        
                        mime = media.GetMime()
                        
                        path = CC.GetFilePath( hash, mime )
                        
                        with open( path, 'rb' ) as f: file = f.read()
                        
                        post_fields.append( ( self._file_post_name, CC.FIELD_FILE, ( hash, mime, file ) ) )
                        
                        ( ct, body ) = CC.GenerateDumpMultipartFormDataCTAndBody( post_fields )
                        
                        headers = {}
                        headers[ 'Content-Type' ] = ct
                        if self._have_4chan_pass: headers[ 'Cookie' ] = 'pass_enabled=1; pass_id=' + self._4chan_token
                        
                        self._actually_dumping = True
                        
                        threading.Thread( target = self._THREADDoDump, args = ( hash, post_field_info, headers, body ) ).start()
                        
                    
                except Exception as e:
                    
                    ( status, phrase ) = ( 'big error', HC.u( e ) )
                    
                    wx.CallAfter( self.CALLBACKDoneDump, hash, post_field_info, status, phrase )
                    
                
            else: self._progress_info.SetLabel( 'dumping next file in ' + HC.u( time_left ) + ' seconds' )
            
        else:
            
            if self._num_dumped == 0: self._progress_info.SetLabel( 'will dump to ' + self._imageboard.GetName() )
            else: self._progress_info.SetLabel( 'paused after ' + HC.u( self._num_dumped ) + ' files dumped' )
            
        
    
    def FocusChanged( self, page_key, media ):
        
        if page_key == self._page_key:
            
            if media is None: hash = None
            else: hash = media.GetHash()
            
            if hash != self._current_hash:
                
                old_hash = self._current_hash
                
                if old_hash is not None: self._FreezeCurrentMediaPostInfo()
                
                self._current_hash = hash
                
                self._ShowCurrentMedia()
                
            
        
    
    def SortedMediaPulse( self, page_key, sorted_media ):
        
        if page_key == self._page_key:
            
            self._sorted_media_hashes = [ media.GetHash() for media in sorted_media ]
            
            self._hashes_to_media = { hash : self._hashes_to_media[ hash ] for hash in self._sorted_media_hashes }
            
            new_hashes_to_dump_info = {}
            
            for ( hash, ( dump_status_enum, dump_status_string, post_field_info ) ) in self._hashes_to_dump_info.items():
                
                if hash not in self._sorted_media_hashes: continue
                
                new_post_field_info = []
                
                for ( name, type, value ) in post_field_info:
                    
                    if type == CC.FIELD_COMMENT:
                        
                        ( initial, append ) = value
                        
                        media = self._hashes_to_media[ hash ]
                        
                        initial = self._GetInitialComment( media )
                        
                        value = ( initial, append )
                        
                    
                    new_post_field_info.append( ( name, type, value ) )
                    
                
                new_hashes_to_dump_info[ hash ] = ( dump_status_enum, dump_status_string, new_post_field_info )
                
            
            self._hashes_to_dump_info = new_hashes_to_dump_info
            
            self._ShowCurrentMedia()
            
            if self._current_hash is None and len( self._sorted_media_hashes ) > 0:
                
                hash_to_select = self._sorted_media_hashes[0]
                
                media_to_select = self._hashes_to_media[ hash_to_select ]
                
                HC.pubsub.pub( 'set_focus', self._page_key, media_to_select )
                
            
        
    
    def TryToClose( self ):
        
        if self._dumping:
            
            with ClientGUIDialogs.DialogYesNo( self, 'This page is still dumping. Are you sure you want to close it?' ) as dlg:
                
                if dlg.ShowModal() == wx.ID_NO: raise Exception()
                
            
        
    
class ManagementPanelImport( ManagementPanel ):
    
    def __init__( self, parent, page, page_key ):
        
        ManagementPanel.__init__( self, parent, page, page_key )
        
        self._successful = 0
        self._failed = 0
        self._deleted = 0
        self._redundant = 0
        
        self._import_queue = []
        self._import_queue_position = 0
        
        self._pause_import = False
        self._cancel_import_queue = threading.Event()
        self._pause_outer_queue = False
        self._cancel_outer_queue = threading.Event()
        
        self._currently_importing = False
        self._currently_processing_import_queue = False
        self._currently_processing_outer_queue = False
        
        self._processing_panel = ClientGUICommon.StaticBox( self, 'progress' )
        
        self._import_overall_info = wx.StaticText( self._processing_panel )
        self._import_current_info = wx.StaticText( self._processing_panel )
        self._import_gauge = ClientGUICommon.Gauge( self._processing_panel )
        
        self._import_pause_button = wx.Button( self._processing_panel, label = 'pause' )
        self._import_pause_button.Bind( wx.EVT_BUTTON, self.EventPauseImport )
        self._import_pause_button.Disable()
        
        self._timer_process_import_queue = wx.Timer( self, id = ID_TIMER_PROCESS_IMPORT_QUEUE )
        
        self.Bind( wx.EVT_TIMER, self.EventProcessImportQueue, id = ID_TIMER_PROCESS_IMPORT_QUEUE )
        
        self._timer_process_import_queue.Start( 1000, wx.TIMER_ONE_SHOT )
        
        HC.pubsub.sub( self, 'ImportDone', 'import_done' )
        HC.pubsub.sub( self, 'SetImportInfo', 'set_import_info' )
        HC.pubsub.sub( self, 'DoneAddingToImportQueue', 'done_adding_to_import_queue' )
        
    
    def _GetPreimportStatus( self ):
        
        status = 'importing ' + HC.u( self._import_queue_position + 1 ) + '/' + HC.u( len( self._import_queue ) )
        
        return status
        
    
    def _GetPreprocessStatus( self ): pass
    
    def _GetStatusStrings( self ):
        
        strs = []
        
        if self._successful > 0: strs.append( HC.u( self._successful ) + ' successful' )
        if self._failed > 0: strs.append( HC.u( self._failed ) + ' failed' )
        if self._deleted > 0: strs.append( HC.u( self._deleted ) + ' already deleted' )
        if self._redundant > 0: strs.append( HC.u( self._redundant ) + ' already in db' )
        
        return strs
        
    
    def _SetButtons( self ):
        
        if self._currently_processing_import_queue: self._import_pause_button.Enable()
        else: self._import_pause_button.Disable()
        
    
    def CALLBACKAddToImportQueue( self, items ):
        
        if self._currently_processing_import_queue: self._import_queue.extend( items )
        else:
            
            self._import_queue = items
            self._import_queue_position = 0
            
            self._timer_process_import_queue.Start( 10, wx.TIMER_ONE_SHOT )
            
            self._currently_processing_import_queue = True
            
            self._SetButtons()
            
        
        self._import_gauge.SetRange( len( self._import_queue ) )
        
    
    def CALLBACKImportArgs( self, path, advanced_import_options, service_identifiers_to_tags, url = None, exception = None ):
        
        if exception is None:
            
            self._import_current_info.SetLabel( self._GetPreimportStatus() )
            
            HC.app.Write( 'import_file_from_page', self._page_key, path, advanced_import_options = advanced_import_options, service_identifiers_to_tags = service_identifiers_to_tags, url = url )
            
        else:
            
            self._currently_importing = False
            self._import_current_info.SetLabel( HC.u( exception ) )
            self._import_gauge.SetValue( self._import_queue_position + 1 )
            self._import_queue_position += 1
            
            self._timer_process_import_queue.Start( 2000, wx.TIMER_ONE_SHOT )
            
        
    
    def DoneAddingToImportQueue( self, page_key ):
        
        if self._page_key == page_key:
            
            self._currently_processing_outer_queue = False
            
            self._SetButtons()
            
        
    
    def EventPauseImport( self, event ):
        
        if self._pause_import:
            
            self._pause_import = False
            
            self._import_pause_button.SetLabel( 'pause' )
            self._import_pause_button.SetForegroundColour( ( 0, 0, 0 ) )
            
        else:
            
            self._pause_import = True
            
            self._import_pause_button.SetLabel( 'resume' )
            self._import_pause_button.SetForegroundColour( ( 0, 128, 0 ) )
            
        
    
    def EventProcessImportQueue( self, event ):
        
        status_strings = self._GetStatusStrings()
        
        self._import_overall_info.SetLabel( ', '.join( status_strings ) )
        
        if self._pause_import or self._paused: self._import_current_info.SetLabel( 'paused' )
        else:
            
            if self._cancel_import_queue.is_set(): self._import_queue = self._import_queue[ : self._import_queue_position ] # cut excess queue
            
            if len( self._import_queue ) == 0: self._import_current_info.SetLabel( '' )
            else:
                
                if not self._currently_importing:
                    
                    if self._import_queue_position < len( self._import_queue ):
                        
                        self._currently_importing = True
                        
                        self._import_current_info.SetLabel( self._GetPreprocessStatus() )
                        
                        item = self._import_queue[ self._import_queue_position ]
                        
                        threading.Thread( target = self._THREADGetImportArgs, args = ( item, ), name = 'Generate Import Args' ).start()
                        
                    else:
                        
                        if self._currently_processing_outer_queue: self._import_current_info.SetLabel( 'waiting for more items' )
                        else:
                            
                            if len( status_strings ) > 0: status = 'import done'
                            else: status = 'import abandoned'
                            
                            self._import_current_info.SetLabel( status )
                            
                            self._currently_processing_import_queue = False
                            
                            self._cancel_import_queue = threading.Event()
                            self._cancel_outer_queue = threading.Event()
                            
                            self._SetButtons()
                            
                        
                    
                
            
        
        self._timer_process_import_queue.Start( 1000, wx.TIMER_ONE_SHOT )
        
    
    def ImportDone( self, page_key, result, exception = None ):
        
        if page_key == self._page_key:
            
            if result == 'successful': self._successful += 1
            elif result == 'failed': self._failed += 1
            elif result == 'deleted': self._deleted += 1
            elif result == 'redundant': self._redundant += 1
            
            self._currently_importing = False
            self._import_gauge.SetValue( self._import_queue_position + 1 )
            self._import_queue_position += 1
            
            if exception is None: self._timer_process_import_queue.Start( 10, wx.TIMER_ONE_SHOT )
            else:
                
                message = os.linesep + 'Had trouble importing ' + HC.u( self._import_queue[ self._import_queue_position - 1 ] ) + ':' + os.linesep + HC.u( exception )
                
                HC.pubsub.pub( 'message', HC.Message( HC.MESSAGE_TYPE_TEXT, message ) )
                
                self._import_current_info.SetLabel( HC.u( exception ) )
                
                self._timer_process_import_queue.Start( 2000, wx.TIMER_ONE_SHOT )
                
            
        
    
    def SetImportInfo( self, page_key, info ):
        
        if self._page_key == page_key: self._import_current_info.SetLabel( info )
        
    
    def TryToClose( self ):
        
        if self._currently_processing_import_queue and not self._pause_import:
            
            with ClientGUIDialogs.DialogYesNo( self, 'This page is still importing. Are you sure you want to close it?' ) as dlg:
                
                if dlg.ShowModal() == wx.ID_NO: raise Exception()
                
            
        
    
class ManagementPanelImportHDD( ManagementPanelImport ):
    
    def __init__( self, parent, page, page_key, paths_info, advanced_import_options = {}, paths_to_tags = {}, delete_after_success = False ):
        
        self._advanced_import_options = advanced_import_options
        self._paths_to_tags = paths_to_tags
        self._delete_after_success = delete_after_success
        
        ManagementPanelImport.__init__( self, parent, page, page_key )
        
        vbox = wx.BoxSizer( wx.VERTICAL )
        
        self._MakeSort( vbox )
        
        self._processing_panel.AddF( self._import_overall_info, FLAGS_EXPAND_PERPENDICULAR )
        self._processing_panel.AddF( self._import_current_info, FLAGS_EXPAND_PERPENDICULAR )
        self._processing_panel.AddF( self._import_gauge, FLAGS_EXPAND_PERPENDICULAR )
        self._processing_panel.AddF( self._import_pause_button, FLAGS_EXPAND_PERPENDICULAR )
        
        vbox.AddF( self._processing_panel, FLAGS_EXPAND_PERPENDICULAR )
        
        self._MakeCurrentSelectionTagsBox( vbox )
        
        self.SetSizer( vbox )
        
        self.CALLBACKAddToImportQueue( paths_info )
        
    
    def _THREADGetImportArgs( self, queue_object ):
        
        try:
            
            self._last_queue_object = queue_object
            
            ( path_type, path_info ) = queue_object
            
            if path_type == 'path':
                
                path = path_info
                
            elif path_type == 'zip':
                
                ( zip_path, name ) = path_info
                
                path = HC.GetTempPath()
                
                with open( path, 'wb' ) as f:
                    
                    with zipfile.ZipFile( zip_path, 'r' ) as z: f.write( z.read( name ) )
                    
                
            
            if path in self._paths_to_tags: service_identifiers_to_tags = self._paths_to_tags[ path ]
            else: service_identifiers_to_tags = {}
            
            wx.CallAfter( self.CALLBACKImportArgs, path, self._advanced_import_options, service_identifiers_to_tags )
            
        except Exception as e:
            
            wx.CallAfter( self.CALLBACKImportArgs, '', {}, {}, exception = e )
            
            raise
            
        
    
    def _GetPreprocessStatus( self ):
        
        status = 'reading ' + HC.u( self._import_queue_position + 1 ) + '/' + HC.u( len( self._import_queue ) )
        
        return status
        
    
    def ImportDone( self, page_key, result, exception = None ):
        
        if page_key == self._page_key:
            
            ManagementPanelImport.ImportDone( self, page_key, result, exception = exception )
            
            if self._delete_after_success and result in ( 'successful', 'redundant' ):
                
                ( path_type, path_info ) = self._last_queue_object
                
                if path_type == 'path':
                    
                    path = path_info
                    
                    try: os.remove( path )
                    except: pass
                    
                
            
        
    
class ManagementPanelImportWithQueue( ManagementPanelImport ):
    
    def __init__( self, parent, page, page_key ):
        
        ManagementPanelImport.__init__( self, parent, page, page_key )
        
        self._download_progress_gauge = ClientGUICommon.Gauge( self._processing_panel )
        
        self._import_cancel_button = wx.Button( self._processing_panel, label = 'that\'s enough' )
        self._import_cancel_button.Bind( wx.EVT_BUTTON, self.EventCancelImport )
        self._import_cancel_button.SetForegroundColour( ( 128, 0, 0 ) )
        self._import_cancel_button.Disable()
        
        self._outer_queue_panel = ClientGUICommon.StaticBox( self, 'queue' )
        
        self._outer_queue_info = wx.StaticText( self._outer_queue_panel )
        
        self._outer_queue = wx.ListBox( self._outer_queue_panel, size = ( -1, 200 ) )
        
        self._new_queue_input = wx.TextCtrl( self._outer_queue_panel, style=wx.TE_PROCESS_ENTER )
        self._new_queue_input.Bind( wx.EVT_KEY_DOWN, self.EventKeyDown )
        
        self._up = wx.Button( self._outer_queue_panel, label = u'\u2191' )
        self._up.Bind( wx.EVT_BUTTON, self.EventUp )
        
        self._remove = wx.Button( self._outer_queue_panel, label = 'X' )
        self._remove.Bind( wx.EVT_BUTTON, self.EventRemove )
        
        self._down = wx.Button( self._outer_queue_panel, label = u'\u2193' )
        self._down.Bind( wx.EVT_BUTTON, self.EventDown )
        
        self._advanced_import_options = ClientGUICommon.AdvancedImportOptions( self )
        
        self._outer_queue_timer = wx.Timer( self, id = ID_TIMER_PROCESS_OUTER_QUEUE )
        
        self.Bind( wx.EVT_TIMER, self.EventProcessOuterQueue, id = ID_TIMER_PROCESS_OUTER_QUEUE )
        
        self._outer_queue_timer.Start( 1000, wx.TIMER_ONE_SHOT )
        
        HC.pubsub.sub( self, 'SetOuterQueueInfo', 'set_outer_queue_info' )
        HC.pubsub.sub( self, 'SetDownloadProgress', 'set_download_progress' )
        
    
    def _GetPreprocessStatus( self ):
        
        status = 'checking url status ' + HC.u( self._import_queue_position + 1 ) + '/' + HC.u( len( self._import_queue ) )
        
        return status
        
    
    def _SetButtons( self ):
        
        if self._currently_processing_import_queue:
            
            self._import_pause_button.Enable()
            self._import_cancel_button.Enable()
            
        else:
            
            self._import_pause_button.Disable()
            self._import_cancel_button.Disable()
            
        
    
    def EventCancelImport( self, event ):
        
        self._cancel_import_queue.set()
        self._cancel_outer_queue.set()
        
        self._import_cancel_button.Disable()
        self._import_pause_button.Disable()
        
        if self._pause_import: self.EventPauseImport( event )
        if self._pause_outer_queue: self.EventPauseOuterQueue( event )
        
    
    def EventPauseOuterQueue( self, event ): pass
    
    def EventKeyDown( self, event ):
        
        if event.KeyCode in ( wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER ):
            
            url = self._new_queue_input.GetValue()
            
            if url != '':
                
                self._outer_queue.Append( url, url )
                
                self._outer_queue_timer.Start( 10, wx.TIMER_ONE_SHOT )
                
                self._new_queue_input.SetValue( '' )
                
            
        else: event.Skip()
        
    
    def EventUp( self, event ):
        
        selection = self._outer_queue.GetSelection()
        
        if selection != wx.NOT_FOUND:
            
            if selection > 0:
                
                url = self._outer_queue.GetClientData( selection )
                
                self._outer_queue.Delete( selection )
                
                self._outer_queue.Insert( url, selection - 1, url )
                
                self._outer_queue.Select( selection - 1 )
                
            
        
    
    def EventProcessOuterQueue( self, event ):
        
        if self._pause_outer_queue: self._outer_queue_info.SetLabel( 'paused' )
        else:
            
            if self._outer_queue.GetCount() > 0 and not self._currently_processing_import_queue and not self._currently_processing_outer_queue:
                
                self._currently_processing_outer_queue = True
                
                item = self._outer_queue.GetClientData( 0 )
                
                self._outer_queue.Delete( 0 )
                
                threading.Thread( target = self._THREADDownloadImportItems, args = ( item, ), name = 'Generate Import Items' ).start()
                
            
        
        self._outer_queue_timer.Start( 1000, wx.TIMER_ONE_SHOT )
        
    
    def EventRemove( self, event ):
        
        selection = self._outer_queue.GetSelection()
        
        if selection != wx.NOT_FOUND: self._outer_queue.Delete( selection )
        
    
    def EventDown( self, event ):
        
        selection = self._outer_queue.GetSelection()
        
        if selection != wx.NOT_FOUND:
            
            if selection + 1 < self._outer_queue.GetCount():
                
                url = self._outer_queue.GetClientData( selection )
                
                self._outer_queue.Delete( selection )
                
                self._outer_queue.Insert( url, selection + 1, url )
                
                self._outer_queue.Select( selection + 1 )
                
            
        
    
    def SetDownloadProgress( self, range, value ):
        
        if range is None: self._download_progress_gauge.Pulse()
        else:
            
            self._download_progress_gauge.SetRange( range )
            self._download_progress_gauge.SetValue( value )
            
        
    
    def SetOuterQueueInfo( self, page_key, info ):
        
        if self._page_key == page_key: self._outer_queue_info.SetLabel( info )
        
    
    def SetImportInfo( self, page_key, info ):
        
        if self._page_key == page_key: self._import_current_info.SetLabel( info )
        
    
    def SetSearchFocus( self, page_key ):
        
        if page_key == self._page_key: self._new_queue_input.SetFocus()
        
    
class ManagementPanelImportWithQueueAdvanced( ManagementPanelImportWithQueue ):
    
    def __init__( self, parent, page, page_key, name, namespaces ):
        
        ManagementPanelImportWithQueue.__init__( self, parent, page, page_key )
        
        self._advanced_tag_options = ClientGUICommon.AdvancedTagOptions( self, 'send ' + name + ' tags to ', namespaces )
        
        self._outer_queue_pause_button = wx.Button( self._outer_queue_panel, label = 'pause' )
        self._outer_queue_pause_button.Bind( wx.EVT_BUTTON, self.EventPauseOuterQueue )
        self._outer_queue_pause_button.Disable()
        
        self._outer_queue_cancel_button = wx.Button( self._outer_queue_panel, label = 'that\'s enough' )
        self._outer_queue_cancel_button.Bind( wx.EVT_BUTTON, self.EventCancelOuterQueue )
        self._outer_queue_cancel_button.SetForegroundColour( ( 128, 0, 0 ) )
        self._outer_queue_cancel_button.Disable()
        
        c_p_hbox = wx.BoxSizer( wx.HORIZONTAL )
        
        c_p_hbox.AddF( self._import_pause_button, FLAGS_EXPAND_BOTH_WAYS )
        c_p_hbox.AddF( self._import_cancel_button, FLAGS_EXPAND_BOTH_WAYS )
        
        
        self._processing_panel.AddF( self._import_overall_info, FLAGS_EXPAND_PERPENDICULAR )
        self._processing_panel.AddF( self._import_current_info, FLAGS_EXPAND_PERPENDICULAR )
        self._processing_panel.AddF( self._download_progress_gauge, FLAGS_EXPAND_PERPENDICULAR )
        self._processing_panel.AddF( self._import_gauge, FLAGS_EXPAND_PERPENDICULAR )
        self._processing_panel.AddF( c_p_hbox, FLAGS_EXPAND_SIZER_PERPENDICULAR )
        
        queue_buttons_vbox = wx.BoxSizer( wx.VERTICAL )
        
        queue_buttons_vbox.AddF( self._up, FLAGS_MIXED )
        queue_buttons_vbox.AddF( self._remove, FLAGS_MIXED )
        queue_buttons_vbox.AddF( self._down, FLAGS_MIXED )
        
        queue_pause_buttons_hbox = wx.BoxSizer( wx.HORIZONTAL )
        
        queue_pause_buttons_hbox.AddF( self._outer_queue_pause_button, FLAGS_EXPAND_BOTH_WAYS )
        queue_pause_buttons_hbox.AddF( self._outer_queue_cancel_button, FLAGS_EXPAND_BOTH_WAYS )
        
        queue_hbox = wx.BoxSizer( wx.HORIZONTAL )
        
        queue_hbox.AddF( self._outer_queue, FLAGS_EXPAND_BOTH_WAYS )
        queue_hbox.AddF( queue_buttons_vbox, FLAGS_MIXED )
        
        self._outer_queue_panel.AddF( queue_pause_buttons_hbox, FLAGS_EXPAND_SIZER_PERPENDICULAR )
        self._outer_queue_panel.AddF( self._outer_queue_info, FLAGS_EXPAND_PERPENDICULAR )
        self._outer_queue_panel.AddF( queue_hbox, FLAGS_EXPAND_SIZER_BOTH_WAYS )
        self._outer_queue_panel.AddF( self._new_queue_input, FLAGS_EXPAND_PERPENDICULAR )
        
        vbox = wx.BoxSizer( wx.VERTICAL )
        
        self._MakeSort( vbox )
        
        vbox.AddF( self._processing_panel, FLAGS_EXPAND_PERPENDICULAR )
        vbox.AddF( self._outer_queue_panel, FLAGS_EXPAND_BOTH_WAYS )
        self._InitExtraVboxElements( vbox )
        vbox.AddF( self._advanced_import_options, FLAGS_EXPAND_PERPENDICULAR )
        vbox.AddF( self._advanced_tag_options, FLAGS_EXPAND_PERPENDICULAR )
        
        self._MakeCurrentSelectionTagsBox( vbox )
        
        self.SetSizer( vbox )
        
        wx.CallAfter( self._new_queue_input.SelectAll )
        
    
    def _InitExtraVboxElements( self, vbox ): pass
    
    def _SetButtons( self ):
        
        if self._currently_processing_import_queue:
            
            self._import_pause_button.Enable()
            self._import_cancel_button.Enable()
            
        else:
            
            self._import_pause_button.Disable()
            self._import_cancel_button.Disable()
            
        
        if self._currently_processing_outer_queue:
            
            self._outer_queue_pause_button.Enable()
            self._outer_queue_cancel_button.Enable()
            
        else:
            
            self._outer_queue_pause_button.Disable()
            self._outer_queue_cancel_button.Disable()
            
        
    
    def _THREADGetImportArgs( self, url_args ):
        
        try:
            
            downloader = self._GetDownloaders( 'example' )[0]
            
            advanced_tag_options = self._advanced_tag_options.GetInfo()
            
            do_tags = len( advanced_tag_options ) > 0
            
            url = url_args[0]
            
            ( status, hash ) = HC.app.Read( 'url_status', url )
            
            if status == 'deleted' and 'exclude_deleted_files' not in self._advanced_import_options.GetInfo(): status = 'new'
            
            if status == 'deleted': HC.pubsub.pub( 'import_done', self._page_key, 'deleted' )
            elif status == 'redundant':
                
                ( media_result, ) = HC.app.Read( 'media_results', HC.LOCAL_FILE_SERVICE_IDENTIFIER, ( hash, ) )
                
                HC.pubsub.pub( 'add_media_results', self._page_key, ( media_result, ) )
                
                if do_tags:
                    
                    tags = downloader.GetTags( *url_args )
                    
                    service_identifiers_to_tags = HydrusDownloading.ConvertTagsToServiceIdentifiersToTags( tags, advanced_tag_options )
                    
                    service_identifiers_to_content_updates = HydrusDownloading.ConvertServiceIdentifiersToTagsToServiceIdentifiersToContentUpdates( hash, service_identifiers_to_tags )
                    
                    HC.app.Write( 'content_updates', service_identifiers_to_content_updates )
                    
                
                HC.pubsub.pub( 'import_done', self._page_key, 'redundant' )
                
            else:
                
                HC.pubsub.pub( 'set_import_info', self._page_key, 'downloading ' + HC.u( self._import_queue_position + 1 ) + '/' + HC.u( len( self._import_queue ) ) )
                
                def hook( range, value ): wx.CallAfter( self.SetDownloadProgress, range, value )
                
                downloader.AddReportHook( hook )
                
                if do_tags: ( file, tags ) = downloader.GetFileAndTags( *url_args )
                else:
                    
                    file = downloader.GetFile( *url_args )
                    
                    tags = []
                    
                
                downloader.ClearReportHooks()
                
                temp_path = HC.GetTempPath()
                
                with open( temp_path, 'wb' ) as f: f.write( file )
                
                service_identifiers_to_tags = HydrusDownloading.ConvertTagsToServiceIdentifiersToTags( tags, advanced_tag_options )
                
                advanced_import_options = self._advanced_import_options.GetInfo()
                
                wx.CallAfter( self.CALLBACKImportArgs, temp_path, advanced_import_options = advanced_import_options, service_identifiers_to_tags = service_identifiers_to_tags, url = url )
                
            
        except Exception as e:
            
            wx.CallAfter( self.CALLBACKImportArgs, self._page_key, '', {}, {}, exception = e )
            
            raise
            
        
    
    def _THREADDownloadImportItems( self, raw_query ):
        
        # this is important, because we'll instantiate new objects in the eventcancel
        
        cancel_import = self._cancel_import_queue
        cancel_download = self._cancel_outer_queue
        
        try:
            
            downloaders = list( self._GetDownloaders( raw_query ) )
            
            downloaders[0].SetupGallerySearch() # for now this is cookie-based for hf, so only have to do it on one
            
            total_urls_found = 0
            
            while True:
                
                downloaders_to_remove = []
                
                for downloader in downloaders:
                    
                    HC.pubsub.pub( 'set_outer_queue_info', self._page_key, 'found ' + HC.u( total_urls_found ) + ' urls' )
                    
                    while self._pause_outer_queue: time.sleep( 1 )
                    
                    if cancel_import.is_set(): break
                    if cancel_download.is_set(): break
                    
                    page_of_url_args = downloader.GetAnotherPage()
                    
                    total_urls_found += len( page_of_url_args )
                    
                    if len( page_of_url_args ) == 0: downloaders_to_remove.append( downloader )
                    else: wx.CallAfter( self.CALLBACKAddToImportQueue, page_of_url_args )
                    
                
                if cancel_import.is_set(): break
                if cancel_download.is_set(): break
                
                for downloader in downloaders_to_remove: downloaders.remove( downloader )
                
                if len( downloaders ) == 0: break
                
            
            HC.pubsub.pub( 'set_outer_queue_info', self._page_key, '' )
            
        finally: HC.pubsub.pub( 'done_adding_to_import_queue', self._page_key )
        
    
    def EventCancelOuterQueue( self, event ):
        
        self._cancel_outer_queue.set()
        
        self._outer_queue_cancel_button.Disable()
        self._outer_queue_pause_button.Disable()
        
        if self._pause_outer_queue: self.EventPauseOuterQueue( event )
        
    
    def EventPauseOuterQueue( self, event ):
        
        if self._pause_outer_queue:
            
            self._pause_outer_queue = False
            
            self._outer_queue_pause_button.SetLabel( 'pause' )
            self._outer_queue_pause_button.SetForegroundColour( ( 0, 0, 0 ) )
            
        else:
            
            self._pause_outer_queue = True
            
            self._outer_queue_pause_button.SetLabel( 'resume' )
            self._outer_queue_pause_button.SetForegroundColour( ( 0, 128, 0 ) )
            
        
    
class ManagementPanelImportWithQueueAdvancedBooru( ManagementPanelImportWithQueueAdvanced ):
    
    def __init__( self, parent, page, page_key, booru ):
        
        self._booru = booru
        
        name = self._booru.GetName()
        namespaces = booru.GetNamespaces()
        
        ManagementPanelImportWithQueueAdvanced.__init__( self, parent, page, page_key, name, namespaces )
        
    
    def _GetDownloaders( self, raw_tags ):
        
        tags = raw_tags.split( ' ' )
        
        return ( HydrusDownloading.GetDownloader( HC.SITE_DOWNLOAD_TYPE_BOORU, self._booru, tags ), )
        
    
class ManagementPanelImportWithQueueAdvancedDeviantArt( ManagementPanelImportWithQueueAdvanced ):
    
    def __init__( self, parent, page, page_key ):
        
        name = 'deviant art'
        namespaces = [ 'creator', 'title', '' ]
        
        ManagementPanelImportWithQueueAdvanced.__init__( self, parent, page, page_key, name, namespaces )
        
        self._new_queue_input.SetValue( 'artist username' )
        
    
    def _GetDownloaders( self, artist ): return ( HydrusDownloading.GetDownloader( HC.SITE_DOWNLOAD_TYPE_DEVIANT_ART, artist ), )
    
class ManagementPanelImportWithQueueAdvancedGiphy( ManagementPanelImportWithQueueAdvanced ):
    
    def __init__( self, parent, page, page_key ):
        
        name = 'giphy'
        namespaces = [ '' ]
        
        ManagementPanelImportWithQueueAdvanced.__init__( self, parent, page, page_key, name, namespaces )
        
        self._new_queue_input.SetValue( 'tag' )
        
    
    def _GetDownloaders( self, tag ): return ( HydrusDownloading.GetDownloader( HC.SITE_DOWNLOAD_TYPE_GIPHY, tag ), )
    
class ManagementPanelImportWithQueueAdvancedHentaiFoundry( ManagementPanelImportWithQueueAdvanced ):
    
    def __init__( self, parent, page, page_key ):
        
        name = 'hentai foundry'
        namespaces = [ 'creator', 'title', '' ]
        
        ManagementPanelImportWithQueueAdvanced.__init__( self, parent, page, page_key, name, namespaces )
        
    
    def _InitExtraVboxElements( self, vbox ):
        
        self._advanced_hentai_foundry_options = ClientGUICommon.AdvancedHentaiFoundryOptions( self )
        
        vbox.AddF( self._advanced_hentai_foundry_options, FLAGS_EXPAND_PERPENDICULAR )
        
    
class ManagementPanelImportWithQueueAdvancedHentaiFoundryArtist( ManagementPanelImportWithQueueAdvancedHentaiFoundry ):
    
    def __init__( self, parent, page, page_key ):
        
        ManagementPanelImportWithQueueAdvancedHentaiFoundry.__init__( self, parent, page, page_key )
        
        self._new_queue_input.SetValue( 'artist username' )
        
    
    def _GetDownloaders( self, artist ):
        
        pictures_downloader = HydrusDownloading.GetDownloader( HC.SITE_DOWNLOAD_TYPE_HENTAI_FOUNDRY, 'artist pictures', artist, self._advanced_hentai_foundry_options.GetInfo() )
        scraps_downloader = HydrusDownloading.GetDownloader( HC.SITE_DOWNLOAD_TYPE_HENTAI_FOUNDRY, 'artist scraps', artist, self._advanced_hentai_foundry_options.GetInfo() )
        
        return ( pictures_downloader, scraps_downloader )
        
    
class ManagementPanelImportWithQueueAdvancedHentaiFoundryTags( ManagementPanelImportWithQueueAdvancedHentaiFoundry ):
    
    def __init__( self, parent, page, page_key ):
        
        ManagementPanelImportWithQueueAdvancedHentaiFoundry.__init__( self, parent, page, page_key )
        
        self._new_queue_input.SetValue( 'search tags' )
        
    
    def _GetDownloaders( self, tags_string ):
        
        tags = tags_string.split( ' ' )
        
        return ( HydrusDownloading.GetDownloader( HC.SITE_DOWNLOAD_TYPE_HENTAI_FOUNDRY, 'tags', tags, self._advanced_hentai_foundry_options.GetInfo() ), )
        
    
class ManagementPanelImportWithQueueAdvancedNewgrounds( ManagementPanelImportWithQueueAdvanced ):
    
    def __init__( self, parent, page, page_key ):
        
        name = 'newgrounds'
        namespaces = [ 'creator', 'title', '' ]
        
        ManagementPanelImportWithQueueAdvanced.__init__( self, parent, page, page_key, name, namespaces )
        
        self._new_queue_input.SetValue( 'artist' )
        
    
    def _GetDownloaders( self, artist ): return ( HydrusDownloading.GetDownloader( HC.SITE_DOWNLOAD_TYPE_NEWGROUNDS, artist ), )
    
class ManagementPanelImportWithQueueAdvancedPixiv( ManagementPanelImportWithQueueAdvanced ):
    
    def __init__( self, parent, page, page_key ):
        
        name = 'pixiv'
        namespaces = [ 'creator', 'title', '' ]
        
        ManagementPanelImportWithQueueAdvanced.__init__( self, parent, page, page_key, name, namespaces )
        
    
class ManagementPanelImportWithQueueAdvancedPixivArtist( ManagementPanelImportWithQueueAdvancedPixiv ):
    
    def __init__( self, parent, page, page_key ):
        
        ManagementPanelImportWithQueueAdvancedPixiv.__init__( self, parent, page, page_key )
        
        self._new_queue_input.SetValue( 'artist id number' )
        
    
    def _GetDownloaders( self, query ): return ( HydrusDownloading.GetDownloader( HC.SITE_DOWNLOAD_TYPE_PIXIV, 'artist', query ), )
    
class ManagementPanelImportWithQueueAdvancedPixivTag( ManagementPanelImportWithQueueAdvancedPixiv ):
    
    def __init__( self, parent, page, page_key ):
        
        ManagementPanelImportWithQueueAdvancedPixiv.__init__( self, parent, page, page_key )
        
        self._new_queue_input.SetValue( 'search tag' )
        
    
    def _GetDownloaders( self, query ): return ( HydrusDownloading.GetDownloader( HC.SITE_DOWNLOAD_TYPE_PIXIV, 'tag', query ), )
    
class ManagementPanelImportWithQueueAdvancedTumblr( ManagementPanelImportWithQueueAdvanced ):
    
    def __init__( self, parent, page, page_key ):
        
        name = 'tumblr'
        namespaces = [ '' ]
        
        ManagementPanelImportWithQueueAdvanced.__init__( self, parent, page, page_key, name, namespaces )
        
        self._new_queue_input.SetValue( 'username' )
        
    
    def _GetDownloaders( self, username ): return ( HydrusDownloading.GetDownloader( HC.SITE_DOWNLOAD_TYPE_TUMBLR, username ), )
    
class ManagementPanelImportWithQueueURL( ManagementPanelImportWithQueue ):
    
    def __init__( self, parent, page, page_key ):
        
        ManagementPanelImportWithQueue.__init__( self, parent, page, page_key )
        
        self._connections = {}
        
        c_p_hbox = wx.BoxSizer( wx.HORIZONTAL )
        
        c_p_hbox.AddF( self._import_pause_button, FLAGS_EXPAND_BOTH_WAYS )
        c_p_hbox.AddF( self._import_cancel_button, FLAGS_EXPAND_BOTH_WAYS )
        
        self._processing_panel.AddF( self._import_overall_info, FLAGS_EXPAND_PERPENDICULAR )
        self._processing_panel.AddF( self._import_current_info, FLAGS_EXPAND_PERPENDICULAR )
        self._processing_panel.AddF( self._download_progress_gauge, FLAGS_EXPAND_PERPENDICULAR )
        self._processing_panel.AddF( self._import_gauge, FLAGS_EXPAND_PERPENDICULAR )
        self._processing_panel.AddF( c_p_hbox, FLAGS_EXPAND_SIZER_PERPENDICULAR )
        
        queue_buttons_vbox = wx.BoxSizer( wx.VERTICAL )
        
        queue_buttons_vbox.AddF( self._up, FLAGS_MIXED )
        queue_buttons_vbox.AddF( self._remove, FLAGS_MIXED )
        queue_buttons_vbox.AddF( self._down, FLAGS_MIXED )
        
        queue_hbox = wx.BoxSizer( wx.HORIZONTAL )
        
        queue_hbox.AddF( self._outer_queue, FLAGS_EXPAND_BOTH_WAYS )
        queue_hbox.AddF( queue_buttons_vbox, FLAGS_MIXED )
        
        self._outer_queue_panel.AddF( self._outer_queue_info, FLAGS_EXPAND_PERPENDICULAR )
        self._outer_queue_panel.AddF( queue_hbox, FLAGS_EXPAND_SIZER_BOTH_WAYS )
        self._outer_queue_panel.AddF( self._new_queue_input, FLAGS_EXPAND_PERPENDICULAR )
        
        vbox = wx.BoxSizer( wx.VERTICAL )
        
        self._MakeSort( vbox )
        
        vbox.AddF( self._processing_panel, FLAGS_EXPAND_PERPENDICULAR )
        vbox.AddF( self._outer_queue_panel, FLAGS_EXPAND_BOTH_WAYS )
        vbox.AddF( self._advanced_import_options, FLAGS_EXPAND_PERPENDICULAR )
        
        self._MakeCurrentSelectionTagsBox( vbox )
        
        self.SetSizer( vbox )
        
    
    def _THREADGetImportArgs( self, queue_object ):
        
        url = queue_object
        
        ( status, hash ) = HC.app.Read( 'url_status', url )
        
        if status == 'deleted' and 'exclude_deleted_files' not in self._advanced_import_options.GetInfo(): status = 'new'
        
        if status == 'deleted': HC.pubsub.pub( 'import_done', self._page_key, 'deleted' )
        elif status == 'redundant':
            
            ( media_result, ) = HC.app.Read( 'media_results', HC.LOCAL_FILE_SERVICE_IDENTIFIER, ( hash, ) )
            
            HC.pubsub.pub( 'add_media_results', self._page_key, ( media_result, ) )
            HC.pubsub.pub( 'import_done', self._page_key, 'redundant' )
            
        else:
            
            HC.pubsub.pub( 'set_import_info', self._page_key, 'downloading ' + HC.u( self._import_queue_position + 1 ) + '/' + HC.u( len( self._import_queue ) ) )
            
            parse_result = urlparse.urlparse( url )
            
            ( scheme, host, port ) = ( parse_result.scheme, parse_result.hostname, parse_result.port )
            
            if ( scheme, host, port ) not in self._connections: self._connections[ ( scheme, host, port ) ] = HC.get_connection( scheme = scheme, host = host, port = port )
            
            connection = self._connections[ ( scheme, host, port ) ]
            
            def hook( range, value ): wx.CallAfter( self.SetDownloadProgress, range, value )
            
            connection.AddReportHook( hook )
            
            temp_path = connection.geturl( url, response_to_path = True )
            
            connection.ClearReportHooks()
            
            advanced_import_options = self._advanced_import_options.GetInfo()
            
            service_identifiers_to_tags = {}
            
            wx.CallAfter( self.CALLBACKImportArgs, temp_path, advanced_import_options, service_identifiers_to_tags, url = url )
            
        
    
    def _THREADDownloadImportItems( self, url ):
        
        try:
            
            HC.pubsub.pub( 'set_outer_queue_info', self._page_key, 'parsing url' )
            
            try:
                
                parse_result = urlparse.urlparse( url )
                
                ( scheme, host, port ) = ( parse_result.scheme, parse_result.hostname, parse_result.port )
                
            except: raise Exception( 'Could not parse that URL' )
            
            HC.pubsub.pub( 'set_outer_queue_info', self._page_key, 'Connecting to address' )
            
            try: connection = HC.get_connection( scheme = scheme, host = host, port = port )
            except: raise Exception( 'Could not connect to server' )
            
            try: html = connection.geturl( url )
            except: raise Exception( 'Could not download that url' )
            
            HC.pubsub.pub( 'set_outer_queue_info', self._page_key, 'parsing html' )
            
            try: urls = ClientParsers.ParsePage( html, url )
            except: raise Exception( 'Could not parse that URL\'s html' )
            
            wx.CallAfter( self.CALLBACKAddToImportQueue, urls )
            
        except Exception as e: HC.pubsub.pub( 'set_outer_queue_info', self._page_key, HC.u( e ) )
        
        HC.pubsub.pub( 'done_adding_to_import_queue', self._page_key )
        
    
class ManagementPanelImportThreadWatcher( ManagementPanelImport ):
    
    def __init__( self, parent, page, page_key ):
        
        ManagementPanelImport.__init__( self, parent, page, page_key )
        
        self._download_progress_gauge = ClientGUICommon.Gauge( self._processing_panel )
        
        self._connections = {}
        
        vbox = wx.BoxSizer( wx.VERTICAL )
        
        self._MakeSort( vbox )
        
        self._processing_panel.AddF( self._import_overall_info, FLAGS_EXPAND_PERPENDICULAR )
        self._processing_panel.AddF( self._import_current_info, FLAGS_EXPAND_PERPENDICULAR )
        self._processing_panel.AddF( self._download_progress_gauge, FLAGS_EXPAND_PERPENDICULAR )
        self._processing_panel.AddF( self._import_gauge, FLAGS_EXPAND_PERPENDICULAR )
        self._processing_panel.AddF( self._import_pause_button, FLAGS_EXPAND_PERPENDICULAR )
        
        self._thread_panel = ClientGUICommon.StaticBox( self, 'thread checker' )
        
        self._thread_info = wx.StaticText( self._thread_panel, label = '' )
        
        self._thread_time = wx.SpinCtrl( self._thread_panel, min = 30, max = 1800 )
        self._thread_time.SetValue( 180 )
        
        self._thread_input = wx.TextCtrl( self._thread_panel, style = wx.TE_PROCESS_ENTER )
        self._thread_input.Bind( wx.EVT_KEY_DOWN, self.EventKeyDown )
        
        self._thread_pause_button = wx.Button( self._thread_panel, label = 'pause' )
        self._thread_pause_button.Bind( wx.EVT_BUTTON, self.EventPauseChecker )
        self._thread_pause_button.SetForegroundColour( ( 128, 0, 0 ) )
        self._thread_pause_button.Disable()
        
        hbox = wx.BoxSizer( wx.HORIZONTAL )
        
        hbox.AddF( wx.StaticText( self._thread_panel, label = 'check every ' ), FLAGS_MIXED )
        hbox.AddF( self._thread_time, FLAGS_MIXED )
        hbox.AddF( wx.StaticText( self._thread_panel, label = ' seconds' ), FLAGS_MIXED )
        
        self._thread_panel.AddF( self._thread_info, FLAGS_EXPAND_PERPENDICULAR )
        self._thread_panel.AddF( self._thread_input, FLAGS_EXPAND_PERPENDICULAR )
        self._thread_panel.AddF( hbox, FLAGS_EXPAND_SIZER_PERPENDICULAR )
        self._thread_panel.AddF( self._thread_pause_button, FLAGS_EXPAND_PERPENDICULAR )
        
        self._advanced_tag_options = ClientGUICommon.AdvancedTagOptions( self, 'send to ', [ 'filename' ] )
        
        self._advanced_import_options = ClientGUICommon.AdvancedImportOptions( self )
        
        vbox.AddF( self._processing_panel, FLAGS_EXPAND_PERPENDICULAR )
        vbox.AddF( self._thread_panel, FLAGS_EXPAND_SIZER_PERPENDICULAR )
        vbox.AddF( self._advanced_tag_options, FLAGS_EXPAND_PERPENDICULAR )
        vbox.AddF( self._advanced_import_options, FLAGS_EXPAND_PERPENDICULAR )
        
        self._MakeCurrentSelectionTagsBox( vbox )
        
        self.SetSizer( vbox )
        
        self._last_thread_check = None
        self._4chan_board = None
        self._thread_id = None
        self._currently_checking_thread = False
        self._currently_paused = False
        self._image_infos_already_added = set()
        
        self._outer_queue_timer = wx.Timer( self, id = ID_TIMER_PROCESS_OUTER_QUEUE )
        
        self.Bind( wx.EVT_TIMER, self.EventProcessOuterQueue, id = ID_TIMER_PROCESS_OUTER_QUEUE )
        
        self._outer_queue_timer.Start( 1000, wx.TIMER_ONE_SHOT )
        
        HC.pubsub.sub( self, 'SetThreadInfo', 'set_thread_info' )
        
    
    def _THREADFetchThread( self ):
        
        HC.pubsub.pub( 'set_thread_info', self._page_key, 'checking thread' )
        
        url = 'http://api.4chan.org/' + self._4chan_board + '/res/' + self._thread_id + '.json'
        
        try:
            
            connection = HC.get_connection( url = url )
            
            raw_json = connection.geturl( url )
            
            json_dict = json.loads( raw_json )
            
            posts_list = json_dict[ 'posts' ]
            
            image_infos = [ ( post[ 'md5' ].decode( 'base64' ), HC.u( post[ 'tim' ] ), post[ 'ext' ], post[ 'filename' ] ) for post in posts_list if 'md5' in post ]
            
            image_infos_i_can_add = [ image_info for image_info in image_infos if image_info not in self._image_infos_already_added ]
            
            self._image_infos_already_added.update( image_infos_i_can_add )
            
            if len( image_infos_i_can_add ) > 0: wx.CallAfter( self.CALLBACKAddToImportQueue, image_infos_i_can_add )
            
        except HydrusExceptions.NotFoundException:
            
            HC.pubsub.pub( 'set_thread_info', self._page_key, 'Thread 404' )
            
            wx.CallAfter( self._thread_pause_button.Disable )
            
            return
            
        except Exception as e:
            
            HC.pubsub.pub( 'set_thread_info', self._page_key, HC.u( e ) )
            
            wx.CallAfter( self._thread_pause_button.Disable )
            
            return
            
        
        self._last_thread_check = HC.GetNow()
        
        self._currently_checking_thread = False
        
    
    def _THREADGetImportArgs( self, queue_object ):
        
        ( md5, image_name, ext, filename ) = queue_object
        
        ( status, hash ) = HC.app.Read( 'md5_status', md5 )
        
        if status == 'deleted' and 'exclude_deleted_files' not in self._advanced_import_options.GetInfo(): status = 'new'
        
        if status == 'deleted': HC.pubsub.pub( 'import_done', self._page_key, 'deleted' )
        elif status == 'redundant':
            
            ( media_result, ) = HC.app.Read( 'media_results', HC.LOCAL_FILE_SERVICE_IDENTIFIER, ( hash, ) )
            
            HC.pubsub.pub( 'add_media_results', self._page_key, ( media_result, ) )
            HC.pubsub.pub( 'import_done', self._page_key, 'redundant' )
            
        else:
            
            url = 'http://images.4chan.org/' + self._4chan_board + '/src/' + image_name + ext
            
            ( status, hash ) = HC.app.Read( 'url_status', url )
            
            if status == 'deleted' and 'exclude_deleted_files' not in self._advanced_import_options.GetInfo(): status = 'new'
            
            if status == 'deleted': HC.pubsub.pub( 'import_done', self._page_key, 'deleted' )
            elif status == 'redundant':
                
                ( media_result, ) = HC.app.Read( 'media_results', HC.LOCAL_FILE_SERVICE_IDENTIFIER, ( hash, ) )
                
                HC.pubsub.pub( 'add_media_results', self._page_key, ( media_result, ) )
                HC.pubsub.pub( 'import_done', self._page_key, 'redundant' )
                
            else:
                
                HC.pubsub.pub( 'set_import_info', self._page_key, 'downloading ' + HC.u( self._import_queue_position + 1 ) + '/' + HC.u( len( self._import_queue ) ) )
                
                parse_result = urlparse.urlparse( url )
                
                ( scheme, host, port ) = ( parse_result.scheme, parse_result.hostname, parse_result.port )
                
                if ( scheme, host, port ) not in self._connections: self._connections[ ( scheme, host, port ) ] = HC.get_connection( scheme = scheme, host = host, port = port )
                
                connection = self._connections[ ( scheme, host, port ) ]
                
                def hook( range, value ): wx.CallAfter( self.SetDownloadProgress, range, value )
                
                connection.AddReportHook( hook )
                
                temp_path = connection.geturl( url, response_to_path = True )
                
                connection.ClearReportHooks()
                
                advanced_import_options = self._advanced_import_options.GetInfo()
                
                advanced_tag_options = self._advanced_tag_options.GetInfo()
                
                tags = [ 'filename:' + filename + ext ]
                
                service_identifiers_to_tags = HydrusDownloading.ConvertTagsToServiceIdentifiersToTags( tags, advanced_tag_options )
                
                wx.CallAfter( self.CALLBACKImportArgs, temp_path, advanced_import_options, service_identifiers_to_tags, url = url )
                
            
        
    
    def _GetPreprocessStatus( self ):
        
        status = 'checking url/hash status ' + HC.u( self._import_queue_position + 1 ) + '/' + HC.u( len( self._import_queue ) )
        
        return status
        
    
    def EventKeyDown( self, event ):
        
        if event.KeyCode in ( wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER ):
            
            url = self._thread_input.GetValue()
            
            if url == '': return
            
            try:
                
                try:
                    
                    parse_result = urlparse.urlparse( url )
                    
                    host = parse_result.hostname
                    
                    request = parse_result.path
                    
                    if host is None or request is None: raise Exception()
                    
                except: raise Exception ( 'Could not understand that url!' )
                
                if host is None or '4chan.org' not in host: raise Exception( 'This only works for 4chan right now!' )
                
                try: ( nothing, board, res, thread_id ) = request.split( '/' )
                except: raise Exception( 'Could not understand the board or thread id!' )
                
            except Exception as e:
                
                self._thread_info.SetLabel( HC.u( e ) )
                
                return
                
            
            self._4chan_board = board
            self._thread_id = thread_id
            
            self._last_thread_check = 0
            
            self._thread_input.Disable()
            self._thread_pause_button.Enable()
            
        else: event.Skip()
        
    
    def EventProcessOuterQueue( self, event ):
        
        if self._4chan_board is None: self._thread_info.SetLabel( 'enter a 4chan thread url' )
        elif self._currently_paused: self._thread_info.SetLabel( 'paused' )
        elif not self._currently_checking_thread:
            
            thread_time = self._thread_time.GetValue()
            
            if thread_time < 30: thread_time = 30
            
            next_thread_check = self._last_thread_check + thread_time
            
            if next_thread_check < HC.GetNow():
                
                self._currently_checking_thread = True
                
                threading.Thread( target = self._THREADFetchThread, name = 'Fetch Thread' ).start()
                
            else: self._thread_info.SetLabel( 'rechecking thread ' + HC.ConvertTimestampToPrettyPending( next_thread_check ) )
            
        
        self._outer_queue_timer.Start( 1000, wx.TIMER_ONE_SHOT )
        
    
    def EventPauseChecker( self, event ):
        
        if self._currently_paused:
            
            self._currently_paused = False
            
            self._thread_pause_button.SetLabel( 'pause' )
            self._thread_pause_button.SetForegroundColour( ( 0, 0, 0 ) )
            
        else:
            
            self._currently_paused = True
            
            self._thread_pause_button.SetLabel( 'resume' )
            self._thread_pause_button.SetForegroundColour( ( 0, 128, 0 ) )
            
        
    
    def SetDownloadProgress( self, range, value ):
        
        if range is None: self._download_progress_gauge.Pulse()
        else:
            
            self._download_progress_gauge.SetRange( range )
            self._download_progress_gauge.SetValue( value )
            
        
    
    def SetSearchFocus( self, page_key ):
        
        if page_key == self._page_key: self._thread_input.SetFocus()
        
    
    def SetThreadInfo( self, page_key, info ):
        
        if self._page_key == page_key: self._thread_info.SetLabel( info )
        
    
class ManagementPanelPetitions( ManagementPanel ):
    
    def __init__( self, parent, page, page_key, file_service_identifier, petition_service_identifier ):
        
        self._petition_service_identifier = petition_service_identifier
        
        ManagementPanel.__init__( self, parent, page, page_key, file_service_identifier )
        
        self._service = HC.app.Read( 'service', self._petition_service_identifier )
        self._can_ban = self._service.GetAccount().HasPermission( HC.MANAGE_USERS )
        
        self._num_petitions = None
        self._current_petition = None
        
        self._petitions_info_panel = ClientGUICommon.StaticBox( self, 'petitions info' )
        
        self._num_petitions_text = wx.StaticText( self._petitions_info_panel )
        
        refresh_num_petitions = wx.Button( self._petitions_info_panel, label = 'refresh' )
        refresh_num_petitions.Bind( wx.EVT_BUTTON, self.EventRefreshNumPetitions )
        
        self._get_petition = wx.Button( self._petitions_info_panel, label = 'get petition' )
        self._get_petition.Bind( wx.EVT_BUTTON, self.EventGetPetition )
        self._get_petition.Disable()
        
        self._petition_panel = ClientGUICommon.StaticBox( self, 'petition' )
        
        self._petition_info_text_ctrl = wx.TextCtrl( self._petition_panel, style = wx.TE_READONLY | wx.TE_MULTILINE )
        
        self._approve = wx.Button( self._petition_panel, label = 'approve' )
        self._approve.Bind( wx.EVT_BUTTON, self.EventApprove )
        self._approve.SetForegroundColour( ( 0, 128, 0 ) )
        self._approve.Disable()
        
        self._deny = wx.Button( self._petition_panel, label = 'deny' )
        self._deny.Bind( wx.EVT_BUTTON, self.EventDeny )
        self._deny.SetForegroundColour( ( 128, 0, 0 ) )
        self._deny.Disable()
        
        self._modify_petitioner = wx.Button( self._petition_panel, label = 'modify petitioner' )
        self._modify_petitioner.Bind( wx.EVT_BUTTON, self.EventModifyPetitioner )
        self._modify_petitioner.Disable()
        if not self._can_ban: self._modify_petitioner.Hide()
        
        num_petitions_hbox = wx.BoxSizer( wx.HORIZONTAL )
        
        num_petitions_hbox.AddF( self._num_petitions_text, FLAGS_EXPAND_BOTH_WAYS )
        num_petitions_hbox.AddF( refresh_num_petitions, FLAGS_MIXED )
        
        self._petitions_info_panel.AddF( num_petitions_hbox, FLAGS_EXPAND_SIZER_PERPENDICULAR )
        self._petitions_info_panel.AddF( self._get_petition, FLAGS_EXPAND_PERPENDICULAR )
        
        p_hbox = wx.BoxSizer( wx.HORIZONTAL )
        
        p_hbox.AddF( self._approve, FLAGS_EXPAND_BOTH_WAYS )
        p_hbox.AddF( self._deny, FLAGS_EXPAND_BOTH_WAYS )
        
        self._petition_panel.AddF( self._petition_info_text_ctrl, FLAGS_EXPAND_BOTH_WAYS )
        self._petition_panel.AddF( p_hbox, FLAGS_EXPAND_SIZER_PERPENDICULAR )
        self._petition_panel.AddF( self._modify_petitioner, FLAGS_EXPAND_PERPENDICULAR )
        
        vbox = wx.BoxSizer( wx.VERTICAL )
        
        self._MakeSort( vbox )
        self._MakeCollect( vbox )
        
        vbox.AddF( self._petitions_info_panel, FLAGS_EXPAND_PERPENDICULAR )
        vbox.AddF( self._petition_panel, FLAGS_EXPAND_BOTH_WAYS )
        
        self._MakeCurrentSelectionTagsBox( vbox )
        
        self.SetSizer( vbox )
        
        wx.CallAfter( self.EventRefreshNumPetitions, None )
        
        HC.pubsub.sub( self, 'RefreshQuery', 'refresh_query' )
        
    
    def _DrawCurrentPetition( self ):
        
        if self._current_petition is None:
            
            self._petition_info_text_ctrl.SetValue( '' )
            self._approve.Disable()
            self._deny.Disable()
            
            if self._can_ban: self._modify_petitioner.Disable()
            
            panel = ClientGUIMedia.MediaPanelNoQuery( self._page, self._page_key, self._file_service_identifier )
            
        else:
            
            self._petition_info_text_ctrl.SetValue( self._current_petition.GetPetitionString() )
            self._approve.Enable()
            self._deny.Enable()
            
            if self._can_ban: self._modify_petitioner.Enable()
            
            with wx.BusyCursor(): media_results = HC.app.Read( 'media_results', self._file_service_identifier, self._current_petition.GetHashes() )
            
            panel = ClientGUIMedia.MediaPanelThumbnails( self._page, self._page_key, self._file_service_identifier, [], media_results )
            
            panel.Collect( self._page_key, self._collect_by.GetChoice() )
            
            panel.Sort( self._page_key, self._sort_by.GetChoice() )
            
        
        HC.pubsub.pub( 'swap_media_panel', self._page_key, panel )
        
    
    def _DrawNumPetitions( self ):
        
        self._num_petitions_text.SetLabel( HC.ConvertIntToPrettyString( self._num_petitions ) + ' petitions' )
        
        if self._num_petitions > 0: self._get_petition.Enable()
        else: self._get_petition.Disable()
        
    
    def EventApprove( self, event ):
        
        update = self._current_petition.GetApproval()
        
        connection = self._service.GetConnection()
        
        connection.Post( 'update', update = update )
        
        HC.app.Write( 'content_updates', { self._petition_service_identifier : update.GetContentUpdates( for_client = True ) } )
        
        self._current_petition = None
        
        self._DrawCurrentPetition()
        
        self.EventRefreshNumPetitions( event )
        
    
    def EventDeny( self, event ):
        
        update = self._current_petition.GetDenial()
        
        connection = self._service.GetConnection()
        
        connection.Post( 'update', update = update )
        
        self._current_petition = None
        
        self._DrawCurrentPetition()
        
        self.EventRefreshNumPetitions( event )
        
    
    def EventGetPetition( self, event ):
        
        try:
            
            connection = self._service.GetConnection()
            
            response = connection.Get( 'petition' )
            
            self._current_petition = response[ 'petition' ]
            
            self._DrawCurrentPetition()
            
        except:
            
            wx.MessageBox( traceback.format_exc() )
            
            self._current_petition = None
            
            self._DrawCurrentPetition()
            
        
    
    def EventModifyPetitioner( self, event ):
        
        with ClientGUIDialogs.DialogModifyAccounts( self, self._petition_service_identifier, ( self._current_petition.GetPetitionerIdentifier(), ) ) as dlg: dlg.ShowModal()
        
    
    def EventRefreshNumPetitions( self, event ):
        
        self._num_petitions_text.SetLabel( u'Fetching\u2026' )
        
        try:
            
            connection = self._service.GetConnection()
            
            response = connection.Get( 'num_petitions' )
            
            self._num_petitions = response[ 'num_petitions' ]
            
            self._DrawNumPetitions()
            
            if self._num_petitions > 0: self.EventGetPetition( event )
            
        except Exception as e: self._num_petitions_text.SetLabel( HC.u( e ) )
        
    
    def RefreshQuery( self, page_key ):
        
        if page_key == self._page_key: self._DrawCurrentPetition()
        
    
class ManagementPanelQuery( ManagementPanel ):
    
    def __init__( self, parent, page, page_key, file_service_identifier, show_search = True, initial_predicates = [] ):
        
        ManagementPanel.__init__( self, parent, page, page_key, file_service_identifier )
        
        self._query_key = HC.JobKey()
        self._synchronised = True
        self._include_current_tags = True
        self._include_pending_tags = True
        
        if show_search:
            
            self._search_panel = ClientGUICommon.StaticBox( self, 'search' )
            
            self._current_predicates_box = ClientGUICommon.TagsBoxPredicates( self._search_panel, self._page_key, initial_predicates )
            
            self._searchbox = ClientGUICommon.AutoCompleteDropdownTagsRead( self._search_panel, self._page_key, self._file_service_identifier, HC.COMBINED_TAG_SERVICE_IDENTIFIER, self._page.GetMedia )
            
            self._search_panel.AddF( self._current_predicates_box, FLAGS_EXPAND_PERPENDICULAR )
            self._search_panel.AddF( self._searchbox, FLAGS_EXPAND_PERPENDICULAR )
            
        
        vbox = wx.BoxSizer( wx.VERTICAL )
        
        self._MakeSort( vbox )
        self._MakeCollect( vbox )
        
        if show_search: vbox.AddF( self._search_panel, FLAGS_EXPAND_PERPENDICULAR )
        
        self._MakeCurrentSelectionTagsBox( vbox )
        
        self.SetSizer( vbox )
        
        if len( initial_predicates ) > 0: wx.CallAfter( self._DoQuery )
        
        HC.pubsub.sub( self, 'AddMediaResultsFromQuery', 'add_media_results_from_query' )
        HC.pubsub.sub( self, 'AddPredicate', 'add_predicate' )
        HC.pubsub.sub( self, 'ChangeFileRepository', 'change_file_repository' )
        HC.pubsub.sub( self, 'ChangeTagRepository', 'change_tag_repository' )
        HC.pubsub.sub( self, 'IncludeCurrent', 'notify_include_current' )
        HC.pubsub.sub( self, 'IncludePending', 'notify_include_pending' )
        HC.pubsub.sub( self, 'SearchImmediately', 'notify_search_immediately' )
        HC.pubsub.sub( self, 'ShowQuery', 'file_query_done' )
        HC.pubsub.sub( self, 'RefreshQuery', 'refresh_query' )
        HC.pubsub.sub( self, 'RemovePredicate', 'remove_predicate' )
        
    
    def _DoQuery( self ):
        
        self._query_key.Cancel()
        
        self._query_key = HC.JobKey()
        
        if self._synchronised:
            
            try:
                
                current_predicates = self._current_predicates_box.GetPredicates()
                
                if len( current_predicates ) > 0:
                    
                    include_current = self._include_current_tags
                    include_pending = self._include_pending_tags
                    
                    search_context = CC.FileSearchContext( self._file_service_identifier, self._tag_service_identifier, include_current, include_pending, current_predicates )
                    
                    HC.app.StartFileQuery( self._query_key, search_context )
                    
                    panel = ClientGUIMedia.MediaPanelLoading( self._page, self._page_key, self._file_service_identifier )
                    
                else: panel = ClientGUIMedia.MediaPanelNoQuery( self._page, self._page_key, self._file_service_identifier )
                
                HC.pubsub.pub( 'swap_media_panel', self._page_key, panel )
                
            except: wx.MessageBox( traceback.format_exc() )
            
        
    
    def AddMediaResultsFromQuery( self, query_key, media_results ):
        
        if query_key == self._query_key: HC.pubsub.pub( 'add_media_results', self._page_key, media_results, append = False )
        
    
    def AddPredicate( self, page_key, predicate ): 
        
        if page_key == self._page_key:
            
            if predicate is not None:
                
                ( predicate_type, value ) = predicate.GetInfo()
                
                if predicate_type == HC.PREDICATE_TYPE_SYSTEM:
                    
                    ( system_predicate_type, info ) = value
                    
                    if system_predicate_type in [ HC.SYSTEM_PREDICATE_TYPE_NUM_TAGS, HC.SYSTEM_PREDICATE_TYPE_LIMIT, HC.SYSTEM_PREDICATE_TYPE_SIZE, HC.SYSTEM_PREDICATE_TYPE_AGE, HC.SYSTEM_PREDICATE_TYPE_HASH, HC.SYSTEM_PREDICATE_TYPE_WIDTH, HC.SYSTEM_PREDICATE_TYPE_HEIGHT, HC.SYSTEM_PREDICATE_TYPE_RATIO, HC.SYSTEM_PREDICATE_TYPE_DURATION, HC.SYSTEM_PREDICATE_TYPE_NUM_WORDS, HC.SYSTEM_PREDICATE_TYPE_MIME, HC.SYSTEM_PREDICATE_TYPE_RATING, HC.SYSTEM_PREDICATE_TYPE_SIMILAR_TO, HC.SYSTEM_PREDICATE_TYPE_FILE_SERVICE ]:
                        
                        with ClientGUIDialogs.DialogInputFileSystemPredicate( self, system_predicate_type ) as dlg:
                            
                            if dlg.ShowModal() == wx.ID_OK: predicate = dlg.GetPredicate()
                            else: return
                            
                        
                    elif system_predicate_type == HC.SYSTEM_PREDICATE_TYPE_UNTAGGED: predicate = HC.Predicate( HC.PREDICATE_TYPE_SYSTEM, ( HC.SYSTEM_PREDICATE_TYPE_NUM_TAGS, ( '=', 0 ) ), None )
                    
                
                if self._current_predicates_box.HasPredicate( predicate ): self._current_predicates_box.RemovePredicate( predicate )
                else: self._current_predicates_box.AddPredicate( predicate )
                
            
            self._DoQuery()
            
        
    
    def ChangeFileRepository( self, page_key, service_identifier ):
        
        if page_key == self._page_key:
            
            self._file_service_identifier = service_identifier
            
            self._DoQuery()
            
        
    
    def ChangeTagRepository( self, page_key, service_identifier ):
        
        if page_key == self._page_key:
            
            self._tag_service_identifier = service_identifier
            
            self._DoQuery()
            
        
    
    def IncludeCurrent( self, page_key, value ):
        
        if page_key == self._page_key:
            
            self._include_current_tags = value
            
            self._DoQuery()
            
        
    
    def IncludePending( self, page_key, value ):
        
        if page_key == self._page_key:
            
            self._include_pending_tags = value
            
            self._DoQuery()
            
        
    
    def RefreshQuery( self, page_key ):
        
        if page_key == self._page_key: self._DoQuery()
        
    
    def RemovePredicate( self, page_key, predicate ):
        
        if page_key == self._page_key:
            
            if self._current_predicates_box.HasPredicate( predicate ):
                
                self._current_predicates_box.RemovePredicate( predicate )
                
                self._DoQuery()
                
            
        
    
    def SearchImmediately( self, page_key, value ):
        
        if page_key == self._page_key:
            
            self._synchronised = value
            
            self._DoQuery()
            
        
    
    def SetSearchFocus( self, page_key ):
        
        if page_key == self._page_key:
            
            try: self._searchbox.SetFocus() # there's a chance this doesn't exist!
            except: pass
            
        
    
    def ShowQuery( self, query_key, media_results ):
        
        try:
            
            if query_key == self._query_key:
                
                current_predicates = self._current_predicates_box.GetPredicates()
                
                panel = ClientGUIMedia.MediaPanelThumbnails( self._page, self._page_key, self._file_service_identifier, current_predicates, media_results )
                
                panel.Collect( self._page_key, self._collect_by.GetChoice() )
                
                panel.Sort( self._page_key, self._sort_by.GetChoice() )
                
                HC.pubsub.pub( 'swap_media_panel', self._page_key, panel )
                
            
        except: wx.MessageBox( traceback.format_exc() )
        
    
class ManagementPanelMessages( wx.ScrolledWindow ):
    
    def __init__( self, parent, page_key, identity ):
        
        wx.ScrolledWindow.__init__( self, parent, style = wx.BORDER_NONE | wx.HSCROLL | wx.VSCROLL )
        
        self.SetScrollRate( 0, 20 )
        
        self._page_key = page_key
        self._identity = identity
        
        self._query_key = HC.JobKey()
        
        # sort out push-refresh later
        #self._refresh_inbox = wx.Button( self, label = 'refresh inbox' )
        #self._refresh_inbox.Bind( wx.EVT_BUTTON, self.EventRefreshInbox )
        #self._refresh_inbox.SetForegroundColour( ( 0, 128, 0 ) )
        
        self._actions_panel = ClientGUICommon.StaticBox( self, 'actions' )
        
        self._compose = wx.Button( self._actions_panel, label = 'compose' )
        self._compose.Bind( wx.EVT_BUTTON, self.EventCompose )
        self._compose.SetForegroundColour( ( 0, 128, 0 ) )
        
        self._actions_panel.AddF( self._compose, FLAGS_EXPAND_PERPENDICULAR )
        #vbox.AddF( self._refresh_inbox, FLAGS_EXPAND_PERPENDICULAR )
        
        self._search_panel = ClientGUICommon.StaticBox( self, 'search' )
        
        self._current_predicates_box = ClientGUICommon.ListBoxMessagesPredicates( self._search_panel, self._page_key, [ 'system:inbox' ] )
        
        self._synchronised = ClientGUICommon.OnOffButton( self._search_panel, self._page_key, 'notify_search_immediately', on_label = 'searching immediately', off_label = 'waiting' )
        self._synchronised.SetToolTipString( 'select whether to renew the search as soon as a new predicate is entered' )
        
        self._searchbox = ClientGUICommon.AutoCompleteDropdownMessageTerms( self._search_panel, self._page_key, self._identity )
        
        self._search_panel.AddF( self._current_predicates_box, FLAGS_EXPAND_BOTH_WAYS )
        self._search_panel.AddF( self._synchronised, FLAGS_EXPAND_PERPENDICULAR )
        self._search_panel.AddF( self._searchbox, FLAGS_EXPAND_PERPENDICULAR )
        
        vbox = wx.BoxSizer( wx.VERTICAL )
        
        vbox.AddF( self._actions_panel, FLAGS_EXPAND_PERPENDICULAR )
        vbox.AddF( self._search_panel, FLAGS_EXPAND_BOTH_WAYS )
        
        self.SetSizer( vbox )
        
        HC.pubsub.sub( self, 'AddPredicate', 'add_predicate' )
        HC.pubsub.sub( self, 'SearchImmediately', 'notify_search_immediately' )
        HC.pubsub.sub( self, 'ShowQuery', 'message_query_done' )
        HC.pubsub.sub( self, 'RefreshQuery', 'refresh_query' )
        HC.pubsub.sub( self, 'RemovePredicate', 'remove_predicate' )
        
        wx.CallAfter( self._DoQuery )
        
    
    def _DoQuery( self ):
        
        if self._synchronised.IsOn():
            
            try:
                
                current_predicates = self._current_predicates_box.GetPredicates()
                
                HC.pubsub.pub( 'set_conversations', self._page_key, [] )
                
                self._query_key.Cancel()
                
                self._query_key = HC.JobKey()
                
                if len( current_predicates ) > 0:
                    
                    search_context = ClientConstantsMessages.MessageSearchContext( self._identity, current_predicates )
                    
                    HC.app.Read( 'do_message_query', self._query_key, search_context )
                    
                
            except: wx.MessageBox( traceback.format_exc() )
            
        
    
    def AddPredicate( self, page_key, predicate ): 
        
        if page_key == self._page_key:
            
            if predicate is not None:
                
                if predicate in ( 'system:started_by', 'system:from', 'system:to', 'system:age', 'system:numattachments' ):
                    
                    with ClientGUIDialogs.DialogInputMessageSystemPredicate( self, predicate ) as dlg:
                        
                        if dlg.ShowModal() == wx.ID_OK: predicate = dlg.GetString()
                        else: return
                        
                    
                elif predicate == 'system:unread': predicate = 'system:status=unread'
                elif predicate == 'system:drafts': predicate = 'system:draft'
                
                if self._current_predicates_box.HasPredicate( predicate ): self._current_predicates_box.RemovePredicate( predicate )
                else:
                    
                    if predicate in ( 'system:inbox', 'system:archive' ):
                        
                        if predicate == 'system:inbox': removee = 'system:archive'
                        elif predicate == 'system:archive': removee = 'system:inbox'
                        
                    else:
                        
                        if predicate.startswith( '-' ): removee = predicate[1:]
                        else: removee = '-' + predicate
                        
                    
                    if self._current_predicates_box.HasPredicate( removee ): self._current_predicates_box.RemovePredicate( removee )
                    
                    self._current_predicates_box.AddPredicate( predicate )
                    
                
            
            self._DoQuery()
            
        
    
    def EventCompose( self, event ): HC.pubsub.pub( 'new_compose_frame', self._identity )
    
    def EventRefreshInbox( self, event ):
        
        # tell db to do it, and that'll spam the appropriate pubsubs (which will tell this to just refresh query, I think is best)
        
        pass
        
    
    def RefreshQuery( self, page_key ):
        
        if page_key == self._page_key: self._DoQuery()
        
    
    def RemovePredicate( self, page_key, predicate ):
        
        if page_key == self._page_key:
            
            if self._current_predicates_box.HasPredicate( predicate ):
                
                self._current_predicates_box.RemovePredicate( predicate )
                
                self._DoQuery()
                
            
        
    
    def SearchImmediately( self, page_key, value ):
        
        if page_key == self._page_key and value: self._DoQuery()
        
    
    def SetSearchFocus( self, page_key ):
        
        if page_key == self._page_key: self._searchbox.SetFocus()
        
    
    def ShowQuery( self, query_key, conversations ):
        
        try:
            
            if query_key == self._query_key: HC.pubsub.pub( 'set_conversations', self._page_key, conversations )
            
        except: wx.MessageBox( traceback.format_exc() )
        
    
    def TryToClose( self ):
        
        pass
        
        # if have a open draft, save it!
        
    